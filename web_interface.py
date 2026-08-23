"""Small local web interface for Voice Reader.

The server intentionally uses only the Python standard library so the desktop
application can expose its browser controls without another install step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import os
import json
import socket
import sys
import threading
import time
import uuid
import wave
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


@dataclass
class _AudioWaiter:
    """Synchronizes one browser clip with the playback thread."""

    event: threading.Event = field(default_factory=threading.Event)
    completed: bool = False


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
        self._audio: dict[str, tuple[bytes, float]] = {}
        self._audio_waiters: dict[str, _AudioWaiter] = {}

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
            self._audio.clear()
            waiters = list(self._audio_waiters.values())
            self._audio_waiters.clear()
            listeners = list(self._listeners)
            self._listeners.clear()

        for waiter in waiters:
            waiter.event.set()
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
            self._audio.clear()
        self._broadcast("state", self.current_state())

    def interrupt_audio(self) -> None:
        """Tell clients to immediately discard their current browser audio."""
        with self._lock:
            waiters = list(self._audio_waiters.values())
            self._audio_waiters.clear()
        for waiter in waiters:
            waiter.event.set()
        self._broadcast("audio-stop", {})

    def publish_wav(self, pcm: bytes, duration: float, volume: float) -> Optional[str]:
        """Store a generated 24kHz mono WAV clip and tell connected clients."""
        if not self.is_running:
            return None

        audio_id = uuid.uuid4().hex
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(pcm)

        with self._lock:
            if not self._listeners:
                return None
            # Prune old clips in case a client leaves mid-playback.
            now = time.monotonic()
            self._audio = {
                key: value for key, value in self._audio.items() if now - value[1] < 300
            }
            self._audio[audio_id] = (output.getvalue(), now)
            self._audio_waiters[audio_id] = _AudioWaiter()
        self._broadcast(
            "audio",
            {
                "id": audio_id,
                "url": f"/api/audio/{audio_id}.wav",
                "duration": duration,
                "volume": max(0.0, min(1.0, volume)),
            },
        )
        return audio_id

    def get_audio(self, audio_id: str) -> Optional[bytes]:
        with self._lock:
            item = self._audio.get(audio_id)
            return item[0] if item else None

    def complete_audio(self, audio_id: str) -> bool:
        """Record that the browser finished playing a specific clip."""
        with self._lock:
            waiter = self._audio_waiters.get(audio_id)
            if waiter is None:
                return False
            waiter.completed = True
            waiter.event.set()
            return True

    def wait_for_audio(self, audio_id: str) -> bool:
        """Wait until the browser ends a clip, or reports/loses playback."""
        with self._lock:
            waiter = self._audio_waiters.get(audio_id)
        if waiter is None:
            return False

        while not waiter.event.wait(timeout=0.1):
            with self._lock:
                if self._listeners:
                    continue
                self._audio_waiters.pop(audio_id, None)
                return False

        with self._lock:
            self._audio_waiters.pop(audio_id, None)
        return waiter.completed

    def add_listener(self, listener: "queue.Queue") -> None:
        with self._lock:
            self._listeners.append(listener)

    def remove_listener(self, listener: "queue.Queue") -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)
            if self._listeners:
                return
            waiters = list(self._audio_waiters.values())
            self._audio_waiters.clear()
        for waiter in waiters:
            waiter.event.set()

    def schedule_control(self, payload: dict) -> tuple[bool, str]:
        action = payload.get("action")
        text = payload.get("text")
        if action not in {"load", "play", "pause", "stop", "back", "forward"}:
            return False, "Unknown control."
        if text is not None and not isinstance(text, str):
            return False, "Text must be a string."

        app = self._get_app()
        if app is None:
            return False, "The desktop reader is not ready."

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
        return True, "Command sent."

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
                app.set_script_contents(text)
                return {"ok": True, "text": text}
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
        if self.path.startswith("/api/audio/") and self.path.endswith(".wav"):
            audio_id = self.path.removeprefix("/api/audio/").removesuffix(".wav")
            audio = self.web_interface.get_audio(audio_id)
            if audio is None:
                self._send(
                    HTTPStatus.NOT_FOUND,
                    "text/plain; charset=utf-8",
                    b"Audio clip expired",
                )
            else:
                self._send(HTTPStatus.OK, "audio/wav", audio)
            return
        self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Not found")

    def do_POST(self) -> None:
        if self.path == "/api/audio-complete":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 1_000:
                    raise ValueError("Request is too large.")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                audio_id = payload.get("id") if isinstance(payload, dict) else None
                if not isinstance(audio_id, str):
                    raise ValueError("Audio id is required.")
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
                self._send(
                    HTTPStatus.BAD_REQUEST,
                    "application/json; charset=utf-8",
                    json.dumps({"ok": False, "message": str(error)}).encode("utf-8"),
                )
                return
            self._send(
                HTTPStatus.OK,
                "application/json; charset=utf-8",
                json.dumps({"ok": self.web_interface.complete_audio(audio_id)}).encode("utf-8"),
            )
            return
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
        ok, message = self.web_interface.schedule_control(payload)
        self._send(
            HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
            "application/json; charset=utf-8",
            json.dumps({"ok": ok, "message": message}).encode("utf-8"),
        )

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
