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
    "ELANA": Character("af_sarah", 1),
    "MIGUEL": Character("bm_daniel", 1),
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

# QUEUE_SIZE = 4000
audio_queue = queue.Queue()

PLAY_AFTER_N_LINES = 6

gen_thread = None


class AudioSample:
    def __init__(self, audio, line, volume_multiplier):
        self.audio = audio
        self.line = line
        self.volume_multiplier = volume_multiplier


# ============================
# AUDIO GENERATION
# ============================


def generate_audio(text, voice,  line, speed, volume_multiplier):
    generator = pipeline(text, voice=voice, speed=speed)
    for _, _, audio in generator:
        if generation_stop.is_set():
            return
        while True:
            try:
                audio_queue.put(AudioSample(audio, line, volume_multiplier), timeout=0.1)
                break
            except queue.Full: #If we cant add to the queue, we must simply drop the audio
                if generation_stop.is_set():
                    return
    audio_queue.put(None)

def clamp(value, min_value, max_value):
    return max(min(value, max_value), min_value)

def queue_script_audio(readerUI, scriptLines):
    generated_lines = 0
    for line in scriptLines:
        if generation_stop.is_set():
            break

        #Only start playback after 3 lines
        generated_lines += 1
        if(generated_lines > PLAY_AFTER_N_LINES): 
            play_event.set()
        
        speed = 1
        if readerUI:
            readerUI.highlight_gen(f"{line.start}.0", f"{line.end}.end")
            speed = readerUI.speed.get()

        character = (
            CHARACTER_VOICES[line.character]
            if line.character in CHARACTER_VOICES
            else NARRATOR_VOICE
        )

        #Calculate how fast to speak a sentence
        speed = clamp(speed * character.speed_multiplier, 0.05, 20)

        generate_audio(line.sentence, character.voice, line,
                        speed=speed, volume_multiplier=character.volume_multiplier)

    #Or playback if there are no lines if less than 3 in the script
    play_event.set()


# ============================
# BUTTON ACTIONS
# ============================


def play(readerUI, text):
    global gen_thread
    readerUI.set_status("Playing...")

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

        if shutdown_event.is_set():
            break

        try:
            sample = audio_queue.get(timeout=0.25)
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
        play_audio(sample.audio, volume_multiplier=sample.volume_multiplier, end_offset=sample.line.end_offset)

    print("Playback thread exited")


play_thread = threading.Thread(target=playback, args=(app,), daemon=True)
play_thread.start()

app.run()
