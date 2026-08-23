"""Port-free desktop web UI for Voice Reader.

The application window is a local ``file://`` page hosted by pywebview. It
does not create an HTTP listener; the separate sharing server is started only
when the user explicitly enables it from the UI.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from ctypes.util import find_library
from pathlib import Path
from typing import Any, Callable, Optional

import characters
import utils


VOICE_OPTIONS = [
    "af_heart", "af_bella", "af_nicole", "af_jessica", "af_sarah",
    "af_sky", "af_nova", "af_kore", "af_river", "af_alloy", "af_aoede",
    "am_adam", "am_michael", "am_eric", "am_liam", "am_echo", "am_onyx",
    "am_fenrir", "am_puck", "bf_alice", "bf_emma", "bf_isabella",
    "bf_lily", "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
]


def resource_path(*parts: str) -> Path:
    """Resolve bundled resources as well as files in a source checkout."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


class _Value:
    """Small, thread-safe replacement for the old Tk variable."""

    def __init__(self, value: float) -> None:
        self._value = value
        self._lock = threading.Lock()

    def get(self) -> float:
        with self._lock:
            return self._value

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value


class _DesktopBridge:
    """Methods exposed to the local HTML page through ``window.pywebview``."""

    def __init__(self, app: "VoiceReaderUI") -> None:
        self._app = app

    def get_state(self) -> dict[str, Any]:
        return self._app.state()

    def set_text(self, text: str) -> dict[str, Any]:
        if not isinstance(text, str):
            return {"ok": False, "message": "Text must be a string."}
        self._app.set_script_contents(text)
        return {"ok": True}

    def read_clipboard(self) -> dict[str, Any]:
        """Read the desktop clipboard without requesting browser permission."""
        return self._app.read_clipboard()

    def control(self, action: str, text: Optional[str] = None) -> dict[str, Any]:
        if action not in {"load", "play", "pause", "stop", "back", "forward"}:
            return {"ok": False, "message": "Unknown control."}
        if text is not None and not isinstance(text, str):
            return {"ok": False, "message": "Text must be a string."}

        if action in {"load", "play"} and text is not None:
            self._app.set_script_contents(text)
        if action == "play":
            self._app.play()
        elif action == "pause":
            self._app.pause()
        elif action == "stop":
            self._app.stop()
        elif action == "back":
            self._app.seek_back()
        elif action == "forward":
            self._app.seek_forward()
        return {"ok": True}

    def set_speed(self, value: Any) -> dict[str, Any]:
        try:
            speed = float(value)
        except (TypeError, ValueError):
            return {"ok": False, "message": "Speed must be a number."}
        self._app.set_speed(speed)
        return {"ok": True}

    def change_font_size(self, delta: Any) -> dict[str, Any]:
        try:
            amount = int(delta)
        except (TypeError, ValueError):
            return {"ok": False, "message": "Font size adjustment is invalid."}
        self._app.change_font_size(amount)
        return {"ok": True}

    def set_mode(self, dialog_mode: bool) -> dict[str, Any]:
        if not isinstance(dialog_mode, bool):
            return {"ok": False, "message": "Mode is invalid."}
        self._app.change_mode(dialog_mode)
        return {"ok": True}

    def characters(self) -> dict[str, Any]:
        return self._app.character_state()

    def select_character(self, name: str) -> dict[str, Any]:
        return self._app.select_character(name)

    def add_character(self) -> dict[str, Any]:
        return self._app.add_character()

    def delete_character(self, name: str) -> dict[str, Any]:
        return self._app.delete_character(name)

    def rename_character(self, old_name: str, new_name: str) -> dict[str, Any]:
        return self._app.rename_character(old_name, new_name)

    def update_character(self, name: str, voice: str, speed: Any, volume: Any) -> dict[str, Any]:
        return self._app.update_character(name, voice, speed, volume)

    def toggle_server(self, port: Any) -> dict[str, Any]:
        return self._app.toggle_web_server(port)


class VoiceReaderUI:
    """The controller used by playback and the pywebview-based desktop UI."""

    def __init__(
        self,
        playRunnable: Optional[Callable] = None,
        stopRunnable: Optional[Callable] = None,
        pauseRunnable: Optional[Callable] = None,
        seekRunnable: Optional[Callable] = None,
        modeChangeRunnable: Optional[Callable] = None,
        webServerRunnable: Optional[Callable] = None,
    ) -> None:
        self.advanced_mode = not os.path.exists("simple-mode.txt")
        self.playRunnable = playRunnable
        self.stopRunnable = stopRunnable
        self.pauseRunnable = pauseRunnable
        self.seekRunnable = seekRunnable
        self.modeChangeRunnable = modeChangeRunnable
        self.webServerRunnable = webServerRunnable
        self.web_server = None

        self.speed = _Value(0.9)
        self.dialog_mode = False
        self._lock = threading.RLock()
        self._script_text = ""
        self._status = "Idle"
        self._font_size = 12
        self._playback_mode = False
        self._generation_lines: Optional[dict[str, int]] = None
        self._playing_lines: Optional[dict[str, int]] = None
        self._seek_lines: Optional[dict[str, int]] = None
        self._server_status = "Share this reader with trusted devices on your network."
        self._selected_character: Optional[str] = None
        self._characters = characters.load_characters(False)
        self._window = None
        self._frontend_ready = False
        self._closed = False
        self._shutdown_callback: Optional[Callable[[], None]] = None
        self._shutdown_notified = False
        self._bridge = _DesktopBridge(self)

    # ------------------------------------------------------------------
    # pywebview lifecycle and state publication
    # ------------------------------------------------------------------

    def set_shutdown_callback(self, callback: Callable[[], None]) -> None:
        self._shutdown_callback = callback

    def _on_loaded(self) -> None:
        self._frontend_ready = True
        self._publish_state()

    def _notify_shutdown(self) -> None:
        if self._shutdown_notified:
            return
        self._shutdown_notified = True
        self._closed = True
        if self._shutdown_callback:
            self._shutdown_callback()

    def state(self) -> dict[str, Any]:
        with self._lock:
            server_running = bool(self.web_server and self.web_server.is_running)
            server_port = self.web_server.port if server_running else None
            return {
                "text": self._script_text,
                "status": self._status,
                "speed": self.speed.get(),
                "dialog_mode": self.dialog_mode,
                "font_size": self._font_size,
                "playback_mode": self._playback_mode,
                "generation_lines": self._generation_lines,
                "playing_lines": self._playing_lines,
                "seek_lines": self._seek_lines,
                "server": {
                    "running": server_running,
                    "port": server_port,
                    "url": self.web_server.url if server_running else "",
                    "message": self._server_status,
                },
                "characters": self._character_state_locked(),
            }

    def _publish_state(self) -> None:
        if self.web_server and self.web_server.is_running:
            self.web_server.broadcast_ui_state()
        if not self._frontend_ready or self._closed or self._window is None:
            return
        # Keep the evaluated JavaScript valid even when the reader text
        # contains Unicode line-separator characters.
        payload = json.dumps(self.state())
        try:
            self._window.evaluate_js(
                "window.VoiceReaderDesktop && "
                f"window.VoiceReaderDesktop.applyState({payload});"
            )
        except Exception:
            # Closing a pywebview window races with background playback updates.
            pass

    def ui(self, fn: Callable[[], None]) -> None:
        """Run a control request without relying on a Tk event loop."""
        try:
            fn()
        except Exception as error:
            self.log(f"ERROR! UI command failed: {error}")

    # ------------------------------------------------------------------
    # Text, highlights, status, and playback helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _line_range(start: str, end: str) -> dict[str, int]:
        def line_number(index: str) -> int:
            try:
                return max(1, int(str(index).split(".", 1)[0]))
            except (TypeError, ValueError):
                return 1

        return {"start_line": line_number(start), "end_line": line_number(end)}

    def set_script_contents(self, text: str, set_margin: bool = True) -> None:
        del set_margin  # Margins are handled by CSS in the HTML editor.
        with self._lock:
            self._script_text = text
        if self.web_server and self.web_server.is_running:
            self.web_server.update_state(text=text)
        self._publish_state()

    @staticmethod
    def read_clipboard() -> dict[str, Any]:
        """Return clipboard text using the host OS instead of WebEngine APIs."""
        if sys.platform.startswith("win"):
            commands = [["powershell", "-NoProfile", "-Command", "Get-Clipboard", "-Raw"]]
        elif sys.platform == "darwin":
            commands = [["pbpaste"]]
        else:
            commands = []
            if os.environ.get("WAYLAND_DISPLAY"):
                commands.append(["wl-paste", "--no-newline"])
            commands.extend(
                [
                    ["xclip", "-selection", "clipboard", "-o"],
                    ["xsel", "--clipboard", "--output"],
                ]
            )

        for command in commands:
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    check=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=3,
                )
                return {"ok": True, "text": result.stdout}
            except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                continue
        return {
            "ok": False,
            "message": "Clipboard access is unavailable. Click in the editor and use Ctrl+V.",
        }

    def get_script_contents(self) -> str:
        with self._lock:
            return self._script_text

    def change_font_size(self, delta: int) -> None:
        with self._lock:
            self._font_size = max(8, min(32, self._font_size + delta))
        self._publish_state()

    def highlight_playback(self, start: str, end: str) -> None:
        with self._lock:
            self._playing_lines = self._line_range(start, end)
        self._publish_state()

    def highlight_gen(self, start: str, end: str) -> None:
        with self._lock:
            self._generation_lines = self._line_range(start, end)
        self._publish_state()

    def highlight_seek(self, start: str, end: str) -> None:
        with self._lock:
            self._seek_lines = self._line_range(start, end)
        self._publish_state()

    def playback_mode(self, isPlaybackMode: bool) -> None:
        with self._lock:
            self._playback_mode = bool(isPlaybackMode)
        self._publish_state()

    def log(self, text: str) -> None:
        print(text)

    def set_status(self, text: str) -> None:
        with self._lock:
            self._status = str(text)
        if self.web_server and self.web_server.is_running:
            self.web_server.update_state(status=str(text))
        self._publish_state()

    # ------------------------------------------------------------------
    # Remote browser audio bridge
    # ------------------------------------------------------------------

    def is_web_audio_active(self) -> bool:
        return bool(self.web_server and self.web_server.is_running)

    def web_begin_buffering(self, text: str) -> None:
        if self.is_web_audio_active():
            self.web_server.begin_buffering(text)

    def web_add_buffered_line(self, text: str, voice: str, start_line: int, end_line: int):
        if self.is_web_audio_active():
            return self.web_server.add_buffered_line(text, voice, start_line, end_line)
        return None

    def web_start_line(self, item_id, text: str, voice: str, start_line: int, end_line: int) -> None:
        if self.is_web_audio_active():
            self.web_server.start_line(item_id, text, voice, start_line, end_line)

    def web_seek_line(self, start_line: int, end_line: int) -> None:
        if self.is_web_audio_active():
            self.web_server.seek_line(start_line, end_line)

    def web_send_audio(self, pcm: bytes, duration: float, volume: float):
        if self.is_web_audio_active():
            return self.web_server.publish_wav(pcm, duration, volume)
        return None

    def web_wait_for_audio(self, audio_id: Optional[str]) -> bool:
        return bool(self.is_web_audio_active() and audio_id and self.web_server.wait_for_audio(audio_id))

    def web_interrupt_audio(self) -> None:
        if self.is_web_audio_active():
            self.web_server.interrupt_audio()

    def web_clear_playback(self) -> None:
        if self.is_web_audio_active():
            self.web_server.clear_playback()

    # ------------------------------------------------------------------
    # Reader controls and sharing server
    # ------------------------------------------------------------------

    def change_mode(self, dialog_mode: Optional[bool] = None) -> None:
        if dialog_mode is not None:
            self.dialog_mode = bool(dialog_mode)
        self._reload_characters()
        if self.modeChangeRunnable:
            self.modeChangeRunnable(self, self.dialog_mode)
        self._publish_state()

    def play(self) -> None:
        if self.playRunnable:
            self.playRunnable(self, self.get_script_contents())

    def pause(self) -> None:
        if self.pauseRunnable:
            self.pauseRunnable(self)

    def seek_back(self) -> None:
        if self.seekRunnable:
            self.seekRunnable(self, -1)

    def seek_forward(self) -> None:
        if self.seekRunnable:
            self.seekRunnable(self, 1)

    def stop(self) -> None:
        if self.stopRunnable:
            self.stopRunnable(self)

    def set_speed(self, value: float) -> None:
        speed = max(0.4, min(2.5, float(value)))
        self.speed.set(speed)
        self._publish_state()

    def toggle_web_server(self, port: Any) -> dict[str, Any]:
        if not self.webServerRunnable:
            return {"ok": False, "message": "Sharing is unavailable."}
        try:
            port_number = int(port)
        except (TypeError, ValueError):
            return {"ok": False, "message": "Enter a valid port number."}

        success, message, running = self.webServerRunnable(self, port_number)
        with self._lock:
            self._server_status = message
        self._publish_state()
        return {
            "ok": success,
            "running": running,
            "message": message,
            "url": self.web_server.url if running else "",
        }

    # ------------------------------------------------------------------
    # Character voice editor
    # ------------------------------------------------------------------

    def _reload_characters(self) -> None:
        with self._lock:
            self._characters = characters.load_characters(self.dialog_mode)
            if self._selected_character not in self._characters:
                self._selected_character = next(iter(self._characters), None)

    def _character_state_locked(self) -> dict[str, Any]:
        return {
            "selected": self._selected_character,
            "items": [
                {
                    "name": name,
                    "voice": character.voice,
                    "speed": character.speed_multiplier,
                    "volume": character.volume_multiplier,
                }
                for name, character in self._characters.items()
            ],
            "voice_options": VOICE_OPTIONS,
        }

    def character_state(self) -> dict[str, Any]:
        with self._lock:
            return self._character_state_locked()

    def _character_response(self, ok: bool, message: str = "") -> dict[str, Any]:
        self._publish_state()
        return {"ok": ok, "message": message, "characters": self.character_state()}

    def select_character(self, name: str) -> dict[str, Any]:
        with self._lock:
            if name not in self._characters:
                return self._character_response(False, "Character not found.")
            self._selected_character = name
        return self._character_response(True)

    def add_character(self) -> dict[str, Any]:
        if not self.dialog_mode:
            return self._character_response(False, "Reader mode has one narrator voice.")
        with self._lock:
            name = "NEW_CHARACTER"
            counter = 1
            while name in self._characters:
                name = f"NEW_CHARACTER_{counter}"
                counter += 1
            self._characters[name] = characters.Character("af_heart", 1.0, 0.5)
            self._selected_character = name
            characters.save_characters(self._characters, self.dialog_mode)
        return self._character_response(True)

    def delete_character(self, name: str) -> dict[str, Any]:
        if not self.dialog_mode:
            return self._character_response(False, "The narrator cannot be deleted in reader mode.")
        with self._lock:
            if name not in self._characters:
                return self._character_response(False, "Character not found.")
            del self._characters[name]
            self._selected_character = next(iter(self._characters), None)
            characters.save_characters(self._characters, self.dialog_mode)
        return self._character_response(True)

    def rename_character(self, old_name: str, new_name: str) -> dict[str, Any]:
        if not self.dialog_mode:
            return self._character_response(False, "Names are fixed in reader mode.")
        normalized = re.sub(r"\s+", " ", str(new_name).strip().upper())
        if not normalized:
            return self._character_response(False, "A character name is required.")
        with self._lock:
            if old_name not in self._characters:
                return self._character_response(False, "Character not found.")
            if normalized != old_name and normalized in self._characters:
                return self._character_response(False, "That character name already exists.")
            if normalized != old_name:
                character = self._characters.pop(old_name)
                self._characters[normalized] = character
                self._selected_character = normalized
                characters.save_characters(self._characters, self.dialog_mode)
        return self._character_response(True)

    def update_character(self, name: str, voice: str, speed: Any, volume: Any) -> dict[str, Any]:
        if voice not in VOICE_OPTIONS:
            return self._character_response(False, "Choose a listed Kokoro voice.")
        with self._lock:
            character = self._characters.get(name)
            if character is None:
                return self._character_response(False, "Character not found.")
            character.voice = voice
            character.speed_multiplier = utils.normalize_float(str(speed), 0.5, 10.0)
            character.volume_multiplier = utils.normalize_float(str(volume), 0.0, 1.0)
            characters.save_characters(self._characters, self.dialog_mode)
        return self._character_response(True)

    def run(self) -> None:
        """Open the desktop HTML page without starting a local web server."""
        # Qt's X11 plugin links this library dynamically. Checking it before
        # Qt starts avoids an otherwise fatal native-plugin error on Debian
        # and Ubuntu systems where it is not installed by default.
        if (
            sys.platform.startswith("linux")
            and os.environ.get("XDG_SESSION_TYPE", "").lower() == "x11"
            and not find_library("xcb-cursor")
        ):
            raise RuntimeError(
                "Voice Reader needs the Linux package libxcb-cursor0 to open "
                "its desktop window. Install it with: sudo apt-get install "
                "libxcb-cursor0"
            )
        try:
            import webview
        except ImportError as error:
            raise RuntimeError(
                "pywebview is required. Install the project requirements and run again."
            ) from error

        self._patch_qt_permission_handler()

        page = resource_path("webapp", "index.html")
        self._window = webview.create_window(
            "Voice Reader",
            url=page.as_uri(),
            js_api=self._bridge,
            width=1200,
            height=750,
            min_size=(900, 600),
        )
        self._window.events.loaded += self._on_loaded
        try:
            # A file URL keeps the desktop UI off the network and avoids port
            # conflicts. The explicit sharing server is independent of this.
            webview.start(gui="qt", http_server=False)
        finally:
            self._notify_shutdown()

    @staticmethod
    def _patch_qt_permission_handler() -> None:
        """Fix pywebview 6.2's callback for recent PyQt6 permission enums.

        pywebview currently passes the old integer constants to
        ``setFeaturePermission``. PyQt6 6.11 requires ``PermissionPolicy``
        enum values and otherwise aborts the entire desktop process when a
        clipboard or media permission is requested.
        """
        try:
            from webview.platforms import qt
        except ImportError:
            return

        page_type = qt.QWebPage
        policy_type = getattr(page_type, "PermissionPolicy", None)
        if policy_type is None:
            return

        media_features = {
            page_type.Feature.MediaAudioCapture,
            page_type.Feature.MediaVideoCapture,
            page_type.Feature.MediaAudioVideoCapture,
        }

        def on_feature_permission_requested(page, origin, feature):
            policy = (
                policy_type.PermissionGrantedByUser
                if feature in media_features
                else policy_type.PermissionDeniedByUser
            )
            page.setFeaturePermission(origin, feature, policy)

        qt.BrowserView.WebPage.onFeaturePermissionRequested = on_feature_permission_requested
