"""Small local web interface for Voice Reader.

The server intentionally uses only the Python standard library so the desktop
application can expose its browser controls without another install step.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import os
import json
import socket
import struct
import sys
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import urlsplit


def _resource_path(*parts: str) -> str:
    """Find browser assets in source runs and PyInstaller bundles."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base, *parts)


# The desktop UI reads these files directly from disk. The sharing server uses
# this explicit allowlist so it exposes the same local assets without serving
# arbitrary files from the application bundle.
_STATIC_ASSETS = {
    "/icon/icon.png": (("icon", "icon.png"), "image/png"),
    "/style.css": (("webapp", "style.css"), "text/css; charset=utf-8"),
    "/main.js": (("webapp", "main.js"), "application/javascript; charset=utf-8"),
    "/vendor/phosphor-icons/regular/style.css": (
        ("webapp", "vendor", "phosphor-icons", "regular", "style.css"),
        "text/css; charset=utf-8",
    ),
    "/vendor/phosphor-icons/regular/Phosphor.woff2": (
        ("webapp", "vendor", "phosphor-icons", "regular", "Phosphor.woff2"),
        "font/woff2",
    ),
}




@dataclass
class _WebState:
    text: str = ""
    status: str = "Idle"
    voice: str = ""
    highlighted_text: str = ""
    highlighted_lines: Optional[dict] = None
    seek_lines: Optional[dict] = None
    buffered_items: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "status": self.status,
            "voice": self.voice,
            "highlighted_text": self.highlighted_text,
            "highlighted_lines": self.highlighted_lines,
            "seek_lines": self.seek_lines,
            "buffered_text": "\n\n".join(item["text"] for item in self.buffered_items),
            "buffered_lines": [
                {
                    "start_line": item["start_line"],
                    "end_line": item["end_line"],
                }
                for item in self.buffered_items
            ],
        }


class _PCMStream:
    """A single, continuous 24 kHz PCM stream for browser playback.

    A mobile browser is allowed to keep an active media resource playing when
    its page is backgrounded, but it may suspend JavaScript between resources.
    Keeping all generated PCM on one HTTP response avoids requiring a browser
    callback between every spoken line.
    """

    def __init__(self, generation: int) -> None:
        self.id = uuid.uuid4().hex
        self.generation = generation
        self._chunks: deque[bytes] = deque()
        self._closed = False
        self._consumer_active = False
        self._changed = threading.Condition()

    def append(self, pcm: bytes) -> bool:
        if not pcm:
            return True
        with self._changed:
            if self._closed:
                return False
            # A stream is normally claimed immediately by the browser.  Keep
            # only a tiny startup allowance so a missing client cannot make a
            # full read accumulate in memory, while a temporarily suspended
            # EventSource connection cannot stop an already-active player.
            if not self._consumer_active and len(self._chunks) >= 4:
                return False
            self._chunks.append(pcm)
            self._changed.notify_all()
            return True

    def claim_consumer(self) -> bool:
        """Allow one browser media connection to consume this live stream."""
        with self._changed:
            if self._closed or self._consumer_active:
                return False
            self._consumer_active = True
            return True

    def release_consumer(self) -> None:
        with self._changed:
            self._consumer_active = False
            self._changed.notify_all()

    def close(self) -> None:
        with self._changed:
            self._closed = True
            self._changed.notify_all()

    def chunks(self):
        """Yield data as it is produced, without ending between speech lines."""
        while True:
            with self._changed:
                self._changed.wait_for(lambda: self._chunks or self._closed)
                if not self._chunks:
                    return
                chunk = self._chunks.popleft()
            yield chunk


def _stream_wav_header() -> bytes:
    """Return a WAV header for a PCM stream whose final length is unknown."""
    # RIFF/WAV length fields are 32-bit.  ``0xffffffff`` is the conventional
    # unknown-length value for a progressive stream; the HTTP response closes
    # when the reader reaches the end.
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        0xFFFFFFFF,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        24000,
        48000,
        2,
        16,
        b"data",
        0xFFFFFFFF,
    )


class WebInterfaceServer:
    """Owns the browser server and the state shared with playback threads."""

    def __init__(self, get_app: Callable[[], object]):
        self._get_app = get_app
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._port: Optional[int] = None
        self._lock = threading.RLock()
        self._state = _WebState()
        self._listeners: list["queue.Queue"] = []
        self._audio_stream: Optional[_PCMStream] = None
        self._audio_generation = 0

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._server is not None

    @property
    def port(self) -> Optional[int]:
        with self._lock:
            return self._port

    def start(self, port: int) -> tuple[bool, str]:
        if not 1 <= port <= 65535:
            return False, "Choose a port between 1 and 65535."

        with self._lock:
            if self._server is not None:
                if self._port == port:
                    return True, self.url
                return (
                    False,
                    f"The web interface is already running on port {self._port}.",
                )

            manager = self

            class Handler(_WebRequestHandler):
                web_interface = manager

            try:
                server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
            except OSError as error:
                return (
                    False,
                    f"Could not start server on port {port}: {error.strerror or error}",
                )

            server.daemon_threads = True
            self._server = server
            self._port = port
            self._thread = threading.Thread(
                target=server.serve_forever,
                name="voice-reader-web-server",
                daemon=True,
            )
            self._thread.start()

        self.update_state(status="Web interface ready")
        return True, self.url

    def stop(self) -> None:
        with self._lock:
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None
            self._port = None
            audio_stream = self._audio_stream
            self._audio_stream = None
            listeners = list(self._listeners)
            self._listeners.clear()

        if audio_stream is not None:
            audio_stream.close()
        for listener in listeners:
            listener.put(None)
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)

    @property
    def url(self) -> str:
        port = self.port
        if port is None:
            return ""
        return f"http://{self._local_ip()}:{port}"

    @staticmethod
    def _local_ip() -> str:
        """Find the LAN address without sending any traffic."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("10.255.255.255", 1))
                return probe.getsockname()[0]
        except OSError:
            return "127.0.0.1"

    def _broadcast(self, event: str, payload: dict) -> None:
        message = (event, json.dumps(payload, ensure_ascii=False))
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener.put(message)

    def broadcast_ui_state(self) -> None:
        """Publish the complete shared UI state after a desktop-only change."""
        self._broadcast("state", self.current_state())

    def update_state(self, **changes: str) -> None:
        with self._lock:
            for name, value in changes.items():
                if hasattr(self._state, name):
                    setattr(self._state, name, value)
        self._broadcast("state", self.current_state())

    def current_state(self) -> dict:
        with self._lock:
            playback_state = self._state.as_dict()

        app = self._get_app()
        if app is None:
            return playback_state

        try:
            state = app.state()
        except Exception:
            return playback_state

        # The playback state is server-owned, while the rest of the shared UI
        # comes from the same controller used by the desktop window.
        state.update(
            {
                "text": playback_state["text"],
                "status": playback_state["status"],
                "voice": playback_state["voice"],
                "highlighted_text": playback_state["highlighted_text"],
                "playing_lines": playback_state["highlighted_lines"],
                "seek_lines": playback_state["seek_lines"],
                "buffered_lines": playback_state["buffered_lines"],
                "remote": True,
            }
        )
        state["server"] = {
            **state.get("server", {}),
            "remote": True,
            "message": "This shared session is managed by the desktop app.",
        }
        return state

    def begin_buffering(self, text: str) -> None:
        with self._lock:
            self._state.text = text
            self._state.highlighted_text = ""
            self._state.highlighted_lines = None
            self._state.seek_lines = None
            self._state.voice = ""
            self._state.buffered_items.clear()
        self._broadcast("state", self.current_state())

    def add_buffered_line(
        self, text: str, voice: str, start_line: int, end_line: int
    ) -> str:
        item_id = uuid.uuid4().hex
        with self._lock:
            self._state.buffered_items.append(
                {
                    "id": item_id,
                    "text": text,
                    "voice": voice,
                    "start_line": start_line,
                    "end_line": end_line,
                }
            )
        self._broadcast("state", self.current_state())
        return item_id

    def start_line(
        self,
        item_id: Optional[str],
        text: str,
        voice: str,
        start_line: int,
        end_line: int,
    ) -> None:
        with self._lock:
            if item_id:
                self._state.buffered_items = [
                    item for item in self._state.buffered_items if item["id"] != item_id
                ]
            self._state.highlighted_text = text
            self._state.highlighted_lines = {
                "start_line": start_line,
                "end_line": end_line,
            }
            self._state.seek_lines = None
            self._state.voice = voice
        self._broadcast("state", self.current_state())

    def seek_line(self, start_line: int, end_line: int) -> None:
        """Show the line selected by the browser's seek controls."""
        with self._lock:
            self._state.seek_lines = {
                "start_line": start_line,
                "end_line": end_line,
            }
        self._broadcast("state", self.current_state())

    def clear_playback(self) -> None:
        self.interrupt_audio()
        with self._lock:
            self._state.highlighted_text = ""
            self._state.highlighted_lines = None
            self._state.seek_lines = None
            self._state.voice = ""
            self._state.buffered_items.clear()
        self._broadcast("state", self.current_state())

    def prepare_audio_stream(self) -> Optional[str]:
        """Start a fresh continuous media resource for a browser read."""
        if not self.is_running:
            return None

        with self._lock:
            previous = self._audio_stream
            previous_generation = self._audio_generation
            self._audio_generation += 1
            stream = _PCMStream(self._audio_generation)
            self._audio_stream = stream

        if previous is not None:
            previous.close()
            # The generation lets a browser ignore this stop notification if
            # its replacement stream arrived first on a separate HTTP request.
            self._broadcast("audio-stop", {"generation": previous_generation})
        url = f"/api/audio-stream/{stream.id}.wav"
        self._broadcast(
            "audio-stream", {"url": url, "generation": stream.generation}
        )
        return url

    @property
    def audio_stream_url(self) -> Optional[str]:
        with self._lock:
            stream = self._audio_stream
            return f"/api/audio-stream/{stream.id}.wav" if stream else None

    def append_stream_audio(self, pcm: bytes) -> bool:
        """Append PCM to the active media resource without a clip boundary."""
        with self._lock:
            stream = self._audio_stream
        return bool(stream and stream.append(pcm))

    def finish_audio_stream(self) -> None:
        """Let a natural playback finish instead of force-pausing the player."""
        with self._lock:
            stream = self._audio_stream
        if stream is not None:
            stream.close()

    def interrupt_audio(self) -> None:
        """Tell clients to immediately discard their current browser audio."""
        with self._lock:
            stream = self._audio_stream
            self._audio_stream = None
            generation = self._audio_generation
        if stream is not None:
            stream.close()
        self._broadcast("audio-stop", {"generation": generation})

    def get_audio_stream(self, stream_id: str) -> Optional[_PCMStream]:
        with self._lock:
            stream = self._audio_stream
            return stream if stream and stream.id == stream_id else None

    def abandon_audio_stream(self, stream: _PCMStream) -> None:
        """Stop producing audio when its only browser media connection drops."""
        with self._lock:
            if self._audio_stream is stream:
                self._audio_stream = None
        stream.close()

    def add_listener(self, listener: "queue.Queue") -> None:
        with self._lock:
            self._listeners.append(listener)

    def remove_listener(self, listener: "queue.Queue") -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def schedule_control(self, payload: dict) -> dict:
        action = payload.get("action")
        text = payload.get("text")
        if action not in {"load", "play", "pause", "stop", "back", "forward"}:
            return {"ok": False, "message": "Unknown control."}
        if text is not None and not isinstance(text, str):
            return {"ok": False, "message": "Text must be a string."}

        app = self._get_app()
        if app is None:
            return {"ok": False, "message": "The desktop reader is not ready."}

        def apply_control() -> None:
            if action in {"load", "play"}:
                loaded_text = text if text is not None else app.get_script_contents()
                app.set_script_contents(loaded_text)
                self.update_state(text=loaded_text)
            if action == "play":
                app.play()
            elif action == "pause":
                app.pause()
            elif action == "stop":
                app.stop()
            elif action == "back":
                app.seek_back()
            elif action == "forward":
                app.seek_forward()

        app.ui(apply_control)
        result = {"ok": True, "message": "Command sent."}
        if action == "play":
            stream_url = self.audio_stream_url
            if stream_url:
                result["stream_url"] = stream_url
                with self._lock:
                    result["stream_generation"] = self._audio_generation
        return result

    def schedule_ui_action(self, payload: dict) -> dict:
        """Apply a non-playback action from the shared version of the UI."""
        action = payload.get("action")
        app = self._get_app()
        if app is None:
            return {"ok": False, "message": "The desktop reader is not ready."}

        try:
            if action == "set_text":
                text = payload.get("text")
                if not isinstance(text, str):
                    raise ValueError("Text must be a string.")
                app.set_script_contents(text)
                self.update_state(text=text)
                return {"ok": True}
            if action == "paste_desktop_clipboard":
                clipboard = app.read_clipboard()
                if not clipboard.get("ok"):
                    return clipboard
                text = clipboard.get("text", "")
                if not isinstance(text, str):
                    raise ValueError("Clipboard text is invalid.")
                html = clipboard.get("html")
                if html is not None and not isinstance(html, str):
                    raise ValueError("Clipboard rich text is invalid.")
                return {"ok": True, "text": text, **({"html": html} if html else {})}
            if action == "set_speed":
                app.set_speed(float(payload.get("value")))
                return {"ok": True}
            if action == "change_font_size":
                app.change_font_size(int(payload.get("delta")))
                return {"ok": True}
            if action == "set_mode":
                dialog_mode = payload.get("dialog_mode")
                if not isinstance(dialog_mode, bool):
                    raise ValueError("Mode is invalid.")
                app.change_mode(dialog_mode)
                return {"ok": True}
            if action == "select_character":
                return app.select_character(payload.get("name"))
            if action == "add_character":
                return app.add_character()
            if action == "delete_character":
                return app.delete_character(payload.get("name"))
            if action == "rename_character":
                return app.rename_character(payload.get("old_name"), payload.get("new_name"))
            if action == "update_character":
                return app.update_character(
                    payload.get("name"),
                    payload.get("voice"),
                    payload.get("speed"),
                    payload.get("volume"),
                )
            if action == "toggle_server":
                return {
                    "ok": False,
                    "message": "Start or stop sharing from the desktop app.",
                }
            raise ValueError("Unknown UI action.")
        except (TypeError, ValueError) as error:
            return {"ok": False, "message": str(error)}


class _WebRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler; a per-server subclass supplies ``web_interface``."""

    web_interface: WebInterfaceServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:
        # Keep the desktop console useful for playback messages.
        return

    def _send(self, status: HTTPStatus, content_type: str, content: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            with open(_resource_path("webapp", "index.html"), encoding="utf-8") as file:
                page = file.read()
            self._send(
                HTTPStatus.OK, "text/html; charset=utf-8", page.encode("utf-8")
            )
            return
        asset = _STATIC_ASSETS.get(urlsplit(self.path).path)
        if asset is not None:
            parts, content_type = asset
            try:
                with open(_resource_path(*parts), "rb") as file:
                    content = file.read()
            except OSError:
                self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Not found")
            else:
                self._send(HTTPStatus.OK, content_type, content)
            return
        if self.path == "/api/state":
            self._send(
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps(self.web_interface.current_state()).encode("utf-8"),
            )
            return
        if self.path == "/api/events":
            self._serve_events()
            return
        if self.path.startswith("/api/audio-stream/") and self.path.endswith(".wav"):
            stream_id = self.path.removeprefix("/api/audio-stream/").removesuffix(".wav")
            stream = self.web_interface.get_audio_stream(stream_id)
            if stream is None:
                self._send(
                    HTTPStatus.NOT_FOUND,
                    "text/plain; charset=utf-8",
                    b"Audio stream expired",
                )
            else:
                self._serve_audio_stream(stream)
            return
        self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Not found")

    def do_POST(self) -> None:
        if self.path == "/api/ui":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 5_000_000:
                    raise ValueError("Request is too large.")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Request body must be an object.")
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
                self._send(
                    HTTPStatus.BAD_REQUEST,
                    "application/json; charset=utf-8",
                    json.dumps({"ok": False, "message": str(error)}).encode("utf-8"),
                )
                return
            result = self.web_interface.schedule_ui_action(payload)
            self._send(
                HTTPStatus.OK if result["ok"] else HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps(result).encode("utf-8"),
            )
            return
        if self.path != "/api/control":
            self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 5_000_000:
                raise ValueError("Text is too large.")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Request body must be an object.")
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
            self._send(
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"ok": False, "message": str(error)}).encode("utf-8"),
            )
            return
        result = self.web_interface.schedule_control(payload)
        self._send(
            HTTPStatus.OK if result["ok"] else HTTPStatus.BAD_REQUEST,
            "application/json; charset=utf-8",
            json.dumps(result).encode("utf-8"),
        )

    def _serve_audio_stream(self, stream: _PCMStream) -> None:
        """Keep one HTTP audio response open while the reader produces PCM."""
        if not stream.claim_consumer():
            self._send(
                HTTPStatus.CONFLICT,
                "text/plain; charset=utf-8",
                b"This live audio stream is already in use.",
            )
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "none")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        disconnected = False
        try:
            self._write_chunk(_stream_wav_header())
            for pcm in stream.chunks():
                self._write_chunk(pcm)
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            disconnected = True
        finally:
            stream.release_consumer()
            if disconnected:
                self.web_interface.abandon_audio_stream(stream)
            # A stream never has a content length, so it owns this connection.
            self.close_connection = True

    def _write_chunk(self, content: bytes) -> None:
        self.wfile.write(f"{len(content):X}\r\n".encode("ascii"))
        self.wfile.write(content)
        self.wfile.write(b"\r\n")
        self.wfile.flush()

    def _serve_events(self) -> None:
        # Imported lazily so the module's non-server users have no extra state.
        import queue

        listener: queue.Queue = queue.Queue()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.web_interface.add_listener(listener)
        listener.put(
            (
                "state",
                json.dumps(self.web_interface.current_state(), ensure_ascii=False),
            )
        )
        try:
            while self.web_interface.is_running:
                try:
                    event, payload = listener.get(timeout=20)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                if event is None:
                    return
                self.wfile.write(f"event: {event}\ndata: {payload}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.web_interface.remove_listener(listener)
