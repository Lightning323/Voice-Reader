"""Small local web interface for Voice Reader.

The server intentionally uses only the Python standard library so the desktop
application can expose its browser controls without another install step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import json
import socket
import threading
import time
import uuid
import wave
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional


WEB_PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Voice Reader</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: #101419; color: #edf2f7; }
    main { width: min(960px, calc(100% - 32px)); margin: 0 auto; padding: 32px 0 48px; }
    h1 { margin: 0 0 4px; font-size: 1.8rem; }
    .subtle { margin: 0 0 24px; color: #98a6b5; }
    .panel, .reading-card { background: #1a2129; border: 1px solid #2c3743; border-radius: 12px; padding: 18px; box-shadow: 0 8px 26px #00000020; }
    textarea { display: block; width: 100%; min-height: 265px; resize: vertical; border: 1px solid #425263; border-radius: 8px; background: #0f151c; color: inherit; padding: 13px; font: 1rem/1.55 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    textarea:focus { outline: 2px solid #4b9fff; outline-offset: 1px; }
    .controls { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 14px; }
    button { border: 0; border-radius: 7px; background: #334152; color: #f5f8fc; padding: 10px 15px; font: inherit; cursor: pointer; }
    button:hover { background: #43566b; }
    button.primary { background: #1677d2; }
    button.primary:hover { background: #2589e6; }
    button.stop { background: #9f3540; }
    button.stop:hover { background: #bd4653; }
    .state { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 18px 0; }
    .stat { background: #1a2129; border: 1px solid #2c3743; border-radius: 10px; padding: 12px 14px; }
    .stat label, .reading-card h2 { display: block; margin: 0 0 5px; color: #9baaba; font-size: .78rem; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }
    .stat span { font-weight: 650; overflow-wrap: anywhere; }
    .reading { display: grid; gap: 12px; }
    .reading-card h2 { margin-bottom: 10px; }
    .reading-card p { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.55; }
    #current { color: #ffd166; font-size: 1.08rem; }
    #buffered { color: #c5d2df; max-height: 180px; overflow: auto; }
    .connection { font-size: .88rem; color: #9baaba; margin-top: 14px; }
    .connection.connected { color: #70d6a2; }
    @media (max-width: 600px) { main { width: min(100% - 22px, 960px); padding-top: 20px; } .state { grid-template-columns: 1fr; } button { flex: 1 1 auto; } }
  </style>
</head>
<body>
  <main>
    <h1>Voice Reader</h1>
    <p class="subtle">Text and controls are connected to the desktop reader.</p>
    <section class="panel">
      <textarea id="text" placeholder="Paste or type text to read…" spellcheck="true"></textarea>
      <div class="controls" aria-label="Playback controls">
        <button id="load">Load text</button>
        <button class="primary" data-action="play">▶ Play</button>
        <button data-action="pause">⏸ Pause</button>
        <button data-action="back">◀ Back</button>
        <button data-action="forward">Forward ▶</button>
        <button class="stop" data-action="stop">■ Stop</button>
      </div>
      <div id="connection" class="connection">Connecting to desktop reader…</div>
    </section>

    <section class="state" aria-live="polite">
      <div class="stat"><label>Status</label><span id="status">Idle</span></div>
      <div class="stat"><label>Voice</label><span id="voice">—</span></div>
    </section>

    <section class="reading">
      <article class="reading-card"><h2>Highlighted text</h2><p id="current">Nothing is being read.</p></article>
      <article class="reading-card"><h2>Buffered text</h2><p id="buffered">The next generated text will appear here.</p></article>
    </section>
  </main>
  <script>
    const text = document.querySelector('#text');
    const status = document.querySelector('#status');
    const voice = document.querySelector('#voice');
    const current = document.querySelector('#current');
    const buffered = document.querySelector('#buffered');
    const connection = document.querySelector('#connection');
    let writingText = false;
    let audioQueue = [];
    let audioPlaying = false;
    let currentSource = null;
    let audioContext = null;
    let audioEpoch = 0;

    async function send(payload) {
      try {
        const response = await fetch('/api/control', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error('The desktop reader did not accept the command.');
      } catch (error) {
        connection.textContent = error.message;
        connection.classList.remove('connected');
      }
    }

    function render(state) {
      status.textContent = state.status || 'Idle';
      voice.textContent = state.voice || '—';
      current.textContent = state.highlighted_text || 'Nothing is being read.';
      buffered.textContent = state.buffered_text || 'The next generated text will appear here.';
      if (!writingText && typeof state.text === 'string') text.value = state.text;
    }

    function unlockAudio() {
      if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)();
      if (audioContext.state === 'suspended') audioContext.resume();
    }

    async function playNextAudio() {
      if (audioPlaying || !audioQueue.length) return;
      const item = audioQueue.shift();
      const epoch = audioEpoch;
      audioPlaying = true;
      try {
        if (!audioContext) unlockAudio();
        const response = await fetch(item.url);
        if (!response.ok) throw new Error('Audio clip expired.');
        const clip = await audioContext.decodeAudioData(await response.arrayBuffer());
        if (epoch !== audioEpoch) return;
        const source = audioContext.createBufferSource();
        const gain = audioContext.createGain();
        source.buffer = clip;
        gain.gain.value = item.volume;
        source.connect(gain).connect(audioContext.destination);
        currentSource = source;
        source.onended = () => {
          if (epoch !== audioEpoch) return;
          if (currentSource === source) currentSource = null;
          audioPlaying = false;
          playNextAudio();
        };
        source.start();
      } catch (error) {
        if (epoch !== audioEpoch) return;
        audioPlaying = false;
        playNextAudio();
      }
    }

    function queueAudio(item) {
      audioQueue.push(item);
      playNextAudio();
    }

    document.querySelector('#load').addEventListener('click', () => send({action: 'load', text: text.value}));
    document.querySelectorAll('[data-action]').forEach((button) => {
      button.addEventListener('click', () => {
        const action = button.dataset.action;
        unlockAudio();
        send({action, ...(action === 'play' ? {text: text.value} : {})});
      });
    });
    text.addEventListener('focus', () => writingText = true);
    text.addEventListener('blur', () => writingText = false);

    const events = new EventSource('/api/events');
    events.addEventListener('state', (event) => render(JSON.parse(event.data)));
    events.addEventListener('audio', (event) => queueAudio(JSON.parse(event.data)));
    events.addEventListener('audio-stop', () => {
      audioEpoch += 1;
      audioQueue = [];
      if (currentSource) currentSource.stop();
      currentSource = null;
      audioPlaying = false;
    });
    events.onopen = () => {
      connection.textContent = 'Connected to desktop reader';
      connection.classList.add('connected');
    };
    events.onerror = () => {
      connection.textContent = 'Connection lost. Retrying…';
      connection.classList.remove('connected');
    };
  </script>
</body>
</html>"""


@dataclass
class _WebState:
    text: str = ""
    status: str = "Idle"
    voice: str = ""
    highlighted_text: str = ""
    buffered_items: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "status": self.status,
            "voice": self.voice,
            "highlighted_text": self.highlighted_text,
            "buffered_text": "\n\n".join(item["text"] for item in self.buffered_items),
        }


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
                return False, f"The web interface is already running on port {self._port}."

            manager = self

            class Handler(_WebRequestHandler):
                web_interface = manager

            try:
                server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
            except OSError as error:
                return False, f"Could not start server on port {port}: {error.strerror or error}"

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
            listeners = list(self._listeners)
            self._listeners.clear()

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

    def update_state(self, **changes: str) -> None:
        with self._lock:
            for name, value in changes.items():
                if hasattr(self._state, name):
                    setattr(self._state, name, value)
            state = self._state.as_dict()
        self._broadcast("state", state)

    def current_state(self) -> dict:
        with self._lock:
            return self._state.as_dict()

    def begin_buffering(self, text: str) -> None:
        with self._lock:
            self._state.text = text
            self._state.highlighted_text = ""
            self._state.voice = ""
            self._state.buffered_items.clear()
            state = self._state.as_dict()
        self._broadcast("state", state)

    def add_buffered_line(self, text: str, voice: str) -> str:
        item_id = uuid.uuid4().hex
        with self._lock:
            self._state.buffered_items.append(
                {"id": item_id, "text": text, "voice": voice}
            )
            state = self._state.as_dict()
        self._broadcast("state", state)
        return item_id

    def start_line(self, item_id: Optional[str], text: str, voice: str) -> None:
        with self._lock:
            if item_id:
                self._state.buffered_items = [
                    item for item in self._state.buffered_items if item["id"] != item_id
                ]
            self._state.highlighted_text = text
            self._state.voice = voice
            state = self._state.as_dict()
        self._broadcast("state", state)

    def clear_playback(self) -> None:
        self.interrupt_audio()
        with self._lock:
            self._state.highlighted_text = ""
            self._state.voice = ""
            self._state.buffered_items.clear()
            self._audio.clear()
            state = self._state.as_dict()
        self._broadcast("state", state)

    def interrupt_audio(self) -> None:
        """Tell clients to immediately discard their current browser audio."""
        self._broadcast("audio-stop", {})

    def publish_wav(self, pcm: bytes, duration: float, volume: float) -> bool:
        """Store a generated 24kHz mono WAV clip and tell connected clients."""
        if not self.is_running:
            return False

        audio_id = uuid.uuid4().hex
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(pcm)

        with self._lock:
            # Prune old clips in case a client leaves mid-playback.
            now = time.monotonic()
            self._audio = {
                key: value
                for key, value in self._audio.items()
                if now - value[1] < 300
            }
            self._audio[audio_id] = (output.getvalue(), now)
        self._broadcast(
            "audio",
            {
                "url": f"/api/audio/{audio_id}.wav",
                "duration": duration,
                "volume": max(0.0, min(1.0, volume)),
            },
        )
        return True

    def get_audio(self, audio_id: str) -> Optional[bytes]:
        with self._lock:
            item = self._audio.get(audio_id)
            return item[0] if item else None

    def add_listener(self, listener: "queue.Queue") -> None:
        with self._lock:
            self._listeners.append(listener)

    def remove_listener(self, listener: "queue.Queue") -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

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
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", WEB_PAGE.encode("utf-8"))
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
                self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Audio clip expired")
            else:
                self._send(HTTPStatus.OK, "audio/wav", audio)
            return
        self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Not found")

    def do_POST(self) -> None:
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
        listener.put(("state", json.dumps(self.web_interface.current_state(), ensure_ascii=False)))
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
