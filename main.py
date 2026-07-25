import queue
import ui
from playback import play_audio

# ============================================================
# KOKORO SETUP
# ============================================================
print("Loading Kokoro...")
from kokoro import KPipeline

pipeline = KPipeline(lang_code="a")
print("Kokoro loaded.")


# ============================================================
# CHARACTER VOICES
"""
🇺🇸 American Female (af_*)
| Voice |	Character |
|--------|-------------|
|af_heart | 	Warm, soft, emotional (default)
|af_bella | 	Expressive, dynamic, one of the best-rated
|af_nicole | 	Professional, clear
|af_jessica | 	Friendly, conversational
|af_sarah | 	Neutral, articulate
|af_sky | 	Bright, energetic
|af_nova | 	Slightly dreamy, gentle
|af_kore | 	Soft, calm
|af_river | 	Relaxed, flowing
|af_alloy | 	Crisp, modern
|af_aoede | 	Musical, lyrical

🇺🇸 American Male (am_*)
|Voice | 	Character|
|--------|-------------|
|am_adam | 	Deep narrator|
|am_michael | 	Natural, casual|
|am_eric | 	Clear, balanced|
|am_liam | 	Youthful|
|am_echo | 	Smooth|
|am_onyx | 	Deeper tone|
|am_fenrir | 	Strong, dramatic|
|am_puck | 	Lighter, energetic|

🇬🇧 British Female (bf_*)
bf_alice
bf_emma
bf_isabella
bf_lily

🇬🇧 British Male (bm_*)
bm_daniel
bm_fable
bm_george
bm_lewis
"""
# ============================================================


class Character:
    def __init__(self, voice, speed_multiplier, volume_multiplier=.5):
        self.voice = voice
        self.speed_multiplier = speed_multiplier
        self.volume_multiplier = volume_multiplier


CHARACTER_VOICES = {
    "RAMIREZ": Character("af_aoede", 1),
    "PATEL": Character("am_eric", 1),
    "CARTER": Character("am_michael", 1, 1),
    "ELANA": Character("af_nicole", 1),
}

NARRATOR_VOICE = Character("am_adam", 1)


# ============================================================
# AUDIO
# ============================================================
import queue
import threading
import scriptParsing

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
    def __init__(self, audio, line):
        self.audio = audio
        self.line = line


# ============================
# AUDIO GENERATION
# ============================


def generate_audio(text, voice, speed, line):
    generator = pipeline(text, voice=voice, speed=speed)
    for _, _, audio in generator:
        if generation_stop.is_set():
            return
        while True:
            try:
                audio_queue.put(AudioSample(audio, line), timeout=0.1)
                break
            except queue.Full:
                if generation_stop.is_set():
                    return
    audio_queue.put(None)

def clamp(value, min_value, max_value):
    return max(min(value, max_value), min_value)

def queue_script_audio(readerUI, scriptLines):
    for line in scriptLines:
        if generation_stop.is_set():
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

        generate_audio(line.sentence, voice.voice, clamp(speed * voice.speed_multiplier, 0.05, 20), line)


# ============================
# BUTTON ACTIONS
# ============================


def play(readerUI, text):
    global gen_thread
    readerUI.set_status("Playing...")

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
    readerUI.set_status("Stopped")

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

def playback(readerUI):
    while not shutdown_event.is_set():
        # Wait until Play is pressed
        play_event.wait()
        # print("Playback thread started")

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
            readerUI.highlight_playback(
                f"{sample.line.start}.0", f"{sample.line.end}.end"
            )
            readerUI.log(f'{sample.line.character}: "{sample.line.sentence}"')
            readerUI.set_status(f"{sample.line.character}")


        characterVoice = (
            CHARACTER_VOICES[sample.line.character]
            if sample.line.character in CHARACTER_VOICES
            else NARRATOR_VOICE
        )
        play_audio(sample.audio, characterVoice.volume_multiplier)

    print("Playback thread exited")


play_thread = threading.Thread(target=playback, args=(app,), daemon=True)
play_thread.start()

app.run()
