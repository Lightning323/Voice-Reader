import argparse
import signal
import sys
import threading
import scriptParsing
import ui
import playback
from playback import (
    playback_thread,
    seek,
    start_playback,
    pause_playback,
    stop_playback,
    shutdown_playback,
    set_audio_index,
    audio_queue,
    generation_stop,
    generation_lock,
    clamp,
)
import characters
from buffering import AudioBuffer
from web_interface import WebInterfaceServer
# ============================================================
# KOKORO SETUP
# ============================================================
pipeline = None
_pipeline_lock = threading.Lock()


def load_pipeline():
    """Load Kokoro only after command-line arguments have been validated."""
    global pipeline
    with _pipeline_lock:
        if pipeline is None:
            print("Loading Kokoro...")
            from kokoro import KPipeline

            pipeline = KPipeline(lang_code="a")
            print("Kokoro loaded.\n")
    return pipeline


# ============================
# AUDIO BUFFERING
# ============================

cached_text = ""
character_voices = {}
audio_buffer = AudioBuffer()


def _current_center_index():
    """Return the script line currently at the playhead, or 0."""
    if len(audio_queue) == 0:
        return 0
    index = clamp(playback.playback_index, 0, len(audio_queue) - 1)
    sample = audio_queue[index]
    if sample is None:
        return 0
    return sample.script_index


# ============================
# BUTTON ACTIONS
# ============================

def play(readerUI, text):
    global character_voices, cached_text

    # Only regenerate if the text has changed or the audio queue is empty
    should_generate = len(audio_queue) == 0 or (text != cached_text)

    if should_generate:
        with generation_lock:
            print("Preparing to Generate... dialog mode:", readerUI.dialog_mode)

            character_voices = characters.load_characters(readerUI.dialog_mode)
            if readerUI.dialog_mode:
                script_lines, new_text = scriptParsing.parse_script(text, character_voices)
                print(len(script_lines), "dialog lines parsed.")
            else:
                script_lines, new_text = scriptParsing.parse_text(text)
                print(len(script_lines), "reader lines parsed.")
                readerUI.set_script_contents(new_text)

            # Make sure we get cached text EXACTLY as it is in the UI
            cached_text = readerUI.get_script_contents()
            load_pipeline()
            audio_buffer.begin(
                readerUI, script_lines, character_voices, load_pipeline, cached_text
            )

    start_playback(readerUI)


def rebuffer(readerUI):
    """Regenerate audio around the playhead after speed or voice changes.

    Playback pauses (if it was playing) and the queue is rebuilt from the
    current position instead of from the very beginning.
    """
    global character_voices, cached_text

    if len(audio_queue) == 0:
        return

    was_playing = playback.allow_playback and not generation_stop.is_set()
    center = _current_center_index()

    if was_playing:
        pause_playback(readerUI)

    character_voices = characters.load_characters(readerUI.dialog_mode)
    text = readerUI.get_script_contents()
    if readerUI.dialog_mode:
        script_lines, _ = scriptParsing.parse_script(text, character_voices)
    else:
        script_lines, _ = scriptParsing.parse_text(text)
    cached_text = text

    load_pipeline()
    audio_buffer.begin(
        readerUI, script_lines, character_voices, load_pipeline, text,
        anchor_index=center,
    )

    if was_playing:
        start_playback(readerUI)


# --------------------------------------------
# Debounced rebuffering for live setting changes
# --------------------------------------------

_rebuffer_thread = None
_rebuffer_pending = False
_rebuffer_condition = threading.Condition()
_rebuffer_target = None


def schedule_rebuffer(readerUI):
    """Debounce repeated speed/character changes into one rebuffer pass."""
    global _rebuffer_thread
    global _rebuffer_pending, _rebuffer_target
    with _rebuffer_condition:
        _rebuffer_target = readerUI
        _rebuffer_pending = True
        _rebuffer_condition.notify()
    if _rebuffer_thread is None:
        _rebuffer_thread = threading.Thread(
            target=_rebuffer_loop, name="voice-reader-rebuffer", daemon=True
        )
        _rebuffer_thread.start()


def _rebuffer_loop():
    global _rebuffer_pending, _rebuffer_target
    while True:
        with _rebuffer_condition:
            while not _rebuffer_pending:
                _rebuffer_condition.wait()
            _rebuffer_pending = False
            target = _rebuffer_target
            # A newer change arriving within the window resets the debounce.
            _rebuffer_condition.wait(timeout=0.35)
            if _rebuffer_pending:
                continue
        rebuffer(target)


def change_mode(readerUI, dialog_mode):
    global character_voices
    stop_playback(readerUI)




# ============================================================
# START APP
# ============================================================

app = None
web_server = WebInterfaceServer(lambda: app)


def toggle_web_server(readerUI, port):
    """Start or stop browser playback from the desktop-side widget."""
    if web_server.is_running:
        # Stop rather than silently switching an in-progress browser read back
        # to the desktop speakers when the server is turned off.
        stop_playback(readerUI)
        web_server.stop()
        return True, "Web interface stopped.", False

    # A newly enabled browser session starts cleanly, so its audio never mixes
    # with a desktop-speaker session that was already in progress.
    stop_playback(readerUI)
    started, detail = web_server.start(port)
    if not started:
        return False, detail, False

    web_server.begin_buffering(readerUI.get_script_contents())
    web_server.update_state(status="Web interface ready")
    return True, f"Open {detail} in a browser on your local network.", True


_shutdown_started = False
play_thread = None


def create_app():
    """Create the shared reader controller used by desktop and headless modes."""
    global app
    if app is None:
        app = ui.VoiceReaderUI(
            playRunnable=play,
            stopRunnable=stop_playback,
            pauseRunnable=pause_playback,
            seekRunnable=seek,
            modeChangeRunnable=change_mode,
            webServerRunnable=toggle_web_server,
            rebufferRunnable=schedule_rebuffer,
        )
        app.web_server = web_server
        app.set_shutdown_callback(shutdown)
    return app


def shutdown():
    global _shutdown_started
    if _shutdown_started:
        return
    _shutdown_started = True
    print("Shutting down...")
    web_server.stop()
    shutdown_playback(app)


def start_playback_thread(reader):
    """Start the single playback worker after the reader is ready."""
    global play_thread
    if play_thread is None or not play_thread.is_alive():
        play_thread = threading.Thread(target=playback_thread, args=(reader,), daemon=True)
        play_thread.start()


def parse_port(value):
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be a number") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description="Read text aloud with Kokoro.")
    parser.add_argument(
        "--hs",
        metavar="PORT",
        type=parse_port,
        help="start the browser server on PORT without opening the desktop UI",
    )
    return parser.parse_args(argv)


def run_headless(port):
    """Run the browser reader without creating a desktop window."""
    reader = create_app()
    success, message, _ = toggle_web_server(reader, port)
    if not success:
        print(message, file=sys.stderr)
        shutdown()
        return 1

    start_playback_thread(reader)
    print(f"Headless server running at {web_server.url}")
    print("Press Ctrl+C to stop.")

    stop_event = threading.Event()

    def request_shutdown(signum, frame):
        del signum, frame
        stop_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    try:
        stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()
    return 0


def main(argv=None):
    arguments = parse_arguments(argv)

    if arguments.hs is not None:
        return run_headless(arguments.hs)

    load_pipeline()
    reader = create_app()
    start_playback_thread(reader)
    reader.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
