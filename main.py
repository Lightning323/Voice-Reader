import queue
import ui
from playback import play_audio
import characters
# ============================================================
# KOKORO SETUP
# ============================================================
print("Loading Kokoro...")
from kokoro import KPipeline

pipeline = KPipeline(lang_code="a")
print("Kokoro loaded.")


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
generated_characters = 0

audio_queue = queue.Queue()
character_voices = {}
narrator_voice = characters.Character("af_heart", 1.0, 0.5)
PLAY_AFTER_N_CHARACTERS = 750

gen_thread = None


class AudioSample:
    def __init__(self, audio, line, volume_multiplier):
        self.audio = audio
        self.line = line
        self.volume_multiplier = volume_multiplier


# ============================
# AUDIO GENERATION
# ============================


def generate_audio(text, voice, line, speed, volume_multiplier):
    global generated_characters

    generator = pipeline(text, voice=voice, speed=speed)
    for _, _, audio in generator:
        if generation_stop.is_set():
            return
        try:
            audio_queue.put(AudioSample(audio, line, volume_multiplier), timeout=0.1)
        finally:
            generated_characters += len(line.text)
            print("Generated:", generated_characters, "/", PLAY_AFTER_N_CHARACTERS)
            if generated_characters > PLAY_AFTER_N_CHARACTERS:
                play_event.set()


def clamp(value, min_value, max_value):
    return max(min(value, max_value), min_value)

def get_character_voice(character):
    if character in character_voices:
        return character_voices[character]
    elif "NARRATOR" in character_voices:
        return character_voices["NARRATOR"]
    return narrator_voice

def queue_script_audio(readerUI, scriptLines):
    global character_voices
    for line in scriptLines:
        if generation_stop.is_set():
            break
        speed = 1
        if readerUI:
            readerUI.highlight_gen(f"{line.start}.0", f"{line.end}.end")
            speed = readerUI.speed.get()

        character = get_character_voice(line.character)

        # Calculate how fast to speak a line
        speed = clamp(
            speed * character.speed_multiplier * line.speed_multiplier, 0.05, 20
        )
        volume_multiplier = character.volume_multiplier

        if line.text.strip() == "":  # We still need to play silence
            audio_queue.put(AudioSample(None, line, volume_multiplier), timeout=0.1)
        else:
            generate_audio(
                line.text,
                character.voice,
                line,
                speed=speed,
                volume_multiplier=volume_multiplier,
            )

    # none to signal end
    audio_queue.put(None)
    # Or playback if there are no lines if less than 3 in the script
    play_event.set()


# ============================
# BUTTON ACTIONS
# ============================


def play(readerUI, text):
    global gen_thread, generated_characters, character_voices

    generated_characters = 0
    readerUI.set_status("Playing...")

    # Stop old generation if any
    generation_stop.set()

    if gen_thread and gen_thread.is_alive():
        gen_thread.join()

    # Clear old audio
    clear_audio_queue()

    generation_stop.clear()

    character_voices = characters.load_characters()
    script_lines = scriptParsing.parse_script(text, character_voices)

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
            stop(readerUI)
            continue

        if readerUI:
            readerUI.highlight_playback(
                f"{sample.line.start}.0", f"{sample.line.end}.end"
            )
            readerUI.log(f'{sample.line.character}: "{sample.line.text}"')
            readerUI.set_status(f"{sample.line.character}")

        print("Playing... ", sample.line, sample.volume_multiplier)
        play_audio(
            sample.audio,
            volume_multiplier=sample.volume_multiplier,
            end_offset=sample.line.end_offset,
        )

    print("Playback thread exited")


play_thread = threading.Thread(target=playback, args=(app,), daemon=True)
play_thread.start()

app.run()
