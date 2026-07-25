import threading
import re
import sounddevice as sd
import queue
import threading
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

finished_generation = False
audio_queue = queue.Queue(maxsize=20)

class AudioSample: #Our class for an audio chunk
    def __init__(self, audio, start, end):
        self.audio = audio
        self.start = start
        self.end = end

def generate_audio(text, voice, speed, start, end):
    generator = pipeline(text, voice=voice, speed=speed)
    for _, _, audio in generator:
        audio_queue.put(AudioSample(audio, start, end))
    audio_queue.put(None)
    print("<GENERATED> ", text)


def queue_script_audio(readerUI, scriptLines):
    try:
        finished_generation = False
        for line in scriptLines:
            if ui.stop_flag:
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
            generate_audio(line.sentence, voice, speed, line.start, line.end)
    finally:
        print("Finished")
        finished_generation = True


def playback(readerUI):
    time.sleep(1)
    while finished_generation is False or ui.stop_flag:
        sample = audio_queue.get()
        if sample is None: #Wait until audio is generated
            time.sleep(1)
            continue

        if readerUI:
            readerUI.highlight_playback(f"{sample.start}.0", f"{sample.end}.end")
        sd.play(sample.audio, samplerate=24000)
        sd.wait()


# ============================================================
# PLAYBACK
# ============================================================


def play(readerUI, text):
    script_lines = scriptParsing.parse_script(text, CHARACTER_VOICES)
    print(len(script_lines), " lines parsed.")

    play_thread = threading.Thread(target=playback, args=(readerUI,), daemon=True)
    play_thread.start()

    gen_thread = threading.Thread(target=queue_script_audio, args=(readerUI, script_lines), daemon=True)
    gen_thread.start()

    # play_thread.join()
    # gen_thread.join()
    print("Playback started")


# ============================================================
# START APP
# ============================================================

app = ui.ScreenplayPlayer(playRunnable=play)
app.run()
