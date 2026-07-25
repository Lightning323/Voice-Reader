
import queue
import ui
import numpy as np

# ============================================================
# KOKORO SETUP
# ============================================================
print("Loading Kokoro...")
from kokoro import KPipeline

pipeline = KPipeline(lang_code="a")
print("Kokoro loaded.")


# ============================================================
# CHARACTER VOICES
# ============================================================

CHARACTER_VOICES = {
    "RAMIREZ": "af_bella",
    "PATEL": "am_eric",
    "CARTER": "am_michael",
    "ELANA": "af_nicole",
}

NARRATOR_VOICE = "am_adam"


# ============================================================
# AUDIO
# ============================================================
import queue
import threading
import scriptParsing
import time

# ============================
# AUDIO STATE
# ============================

play_event = threading.Event()  # Playback allowed
shutdown_event = threading.Event()  # App closing
generation_stop = threading.Event()  # Stop current generation

QUEUE_SIZE = 20
audio_queue = queue.Queue(maxsize=QUEUE_SIZE)

gen_thread = None


class AudioSample:
    def __init__(self, audio, start, end):
        self.audio = audio
        self.start = start
        self.end = end


# ============================
# AUDIO GENERATION
# ============================


def generate_audio(text, voice, speed, start, end):
    generator = pipeline(text, voice=voice, speed=speed)
    for _, _, audio in generator:
        if generation_stop.is_set():
            return
        while True:
            try:
                audio_queue.put(AudioSample(audio, start, end), timeout=0.1)
                break
            except queue.Full:
                if generation_stop.is_set():
                    return
    audio_queue.put(None)


def queue_script_audio(readerUI, scriptLines):
    for line in scriptLines:
        if generation_stop.is_set():
            break
        speed = 1
        if readerUI:
            readerUI.log(f'{line.character}: "{line.sentence}"')
            readerUI.highlight_gen(f"{line.start}.0", f"{line.end}.end")
            speed = readerUI.speed.get()

        voice = (
            CHARACTER_VOICES[line.character]
            if line.character in CHARACTER_VOICES
            else NARRATOR_VOICE
        )
        generate_audio(line.sentence, voice, speed, line.start, line.end)


# ============================
# BUTTON ACTIONS
# ============================


def play(readerUI, text):
    global gen_thread

    # Resume playback
    play_event.set()

    # Stop old generation if any
    generation_stop.set()

    if gen_thread and gen_thread.is_alive():
        gen_thread.join()

    # Clear old audio
    clear_audio_queue()

    generation_stop.clear()

    script_lines = scriptParsing.parse_script(text, CHARACTER_VOICES)

    print(len(script_lines), "lines parsed.")

    gen_thread = threading.Thread(
        target=queue_script_audio, args=(readerUI, script_lines), daemon=True
    )
    gen_thread.start()
    readerUI.log("Playback started")


def stop(readerUI):
    global gen_thread

    # Pause playback
    play_event.clear()

    # Stop generating
    generation_stop.set()

    clear_audio_queue()
    readerUI.log("Playback stopped...")


def clear_audio_queue():
    while not audio_queue.empty():
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            break


# ============================================================
# START APP
# ============================================================

app = ui.ScreenplayPlayer(playRunnable=play, stopRunnable=stop)


def shutdown():
    print("Shutting down...")
    shutdown_event.set()
    play_event.set()
    app.root.destroy()


app.root.protocol("WM_DELETE_WINDOW", shutdown)


# ============================
# PERMANENT PLAYBACK THREAD
# ============================

import pygame

pygame.mixer.init(
    frequency=24000,
    size=-16,
    channels=1
)

def play_audio(audio):
    audio = (
        audio.detach()
        .cpu()
        .numpy()
        .flatten()
    )

    audio = np.clip(
        audio * 32767,
        -32768,
        32767
    ).astype(np.int16)

    sound = pygame.mixer.Sound(buffer=audio.tobytes())
    delay = max(0, sound.get_length())
    sound.play()
    # print(delay)
    time.sleep(delay)

def playback(readerUI):
    while not shutdown_event.is_set():
        # Wait until Play is pressed
        play_event.wait()
        print("Playback thread started")

        if shutdown_event.is_set():
            break

        try:
            sample = audio_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        # End marker
        if sample is None:
            continue

        if readerUI:
            readerUI.highlight_playback(f"{sample.start}.0", f"{sample.end}.end")
        play_audio(sample.audio)

    print("Playback thread exited")


play_thread = threading.Thread(target=playback, args=(app,), daemon=True)
play_thread.start()

app.run()
