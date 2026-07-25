import sounddevice as sd
import queue
import ui

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

stop_event = threading.Event()
finished_generation = threading.Event()

QUEUE_SIZE = 10
audio_queue = queue.Queue(maxsize=QUEUE_SIZE)

play_thread = None
gen_thread = None

class AudioSample: #Our class for an audio chunk
    def __init__(self, audio, start, end):
        self.audio = audio
        self.start = start
        self.end = end

def generate_audio(text, voice, speed, start, end, stop_event):
    generator = pipeline(text, voice=voice, speed=speed)
    for _, _, audio in generator:
        if stop_event.is_set():
            return
        audio_queue.put(AudioSample(audio, start, end))
    audio_queue.put(None)

def queue_script_audio(readerUI, scriptLines, stop_event):
    try:
        for line in scriptLines:
            if stop_event.is_set():
                break
            speed = 1
            if readerUI:
                readerUI.highlight_gen(f"{line.start}.0", f"{line.end}.end")
                speed = readerUI.speed.get()
            voice = (
                CHARACTER_VOICES[line.character]
                if line.character in CHARACTER_VOICES
                else NARRATOR_VOICE
            )
            generate_audio(
                line.sentence,
                voice,
                speed,
                line.start,
                line.end,
                stop_event
            )
    finally:
        print("Finished generation")
        finished_generation.set()

def playback(readerUI, stop_event):
    time.sleep(1)
    while not stop_event.is_set() or not finished_generation.is_set():
        try:
            sample = audio_queue.get(timeout=0.5)
        except queue.Empty:
            time.sleep(1)
            continue

        if sample:
            if readerUI:
                readerUI.highlight_playback(f"{sample.start}.0", f"{sample.end}.end")
            sd.play(sample.audio, samplerate=24000)
            sd.wait()


def play(readerUI, text):
    global play_thread, gen_thread, audio_queue

    stop_event.clear()
    finished_generation.clear()

    script_lines = scriptParsing.parse_script(text, CHARACTER_VOICES)
    print(len(script_lines), "lines parsed.")

    play_thread = threading.Thread(
        target=playback,
        args=(readerUI, stop_event),
        daemon=True
    )
    play_thread.start()

    gen_thread = threading.Thread(
        target=queue_script_audio,
        args=(readerUI, script_lines, stop_event),
        daemon=True
    )
    gen_thread.start()

    readerUI.log("Playback started")


def stop(readerUI):
    stop_event.set()
    sd.stop()

    while not audio_queue.empty():
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            break

    readerUI.log("Stopping playback...")

# ============================================================
# START APP
# ============================================================

app = ui.ScreenplayPlayer(playRunnable=play, stopRunnable=stop)
app.run()
