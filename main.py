import ui
import threading
import scriptParsing
from playback import playback_thread, seek, start_playback, pause_playback, stop_playback, shutdown_playback,  audio_queue, generation_stop,generation_lock, set_audio_index
import characters
# ============================================================
# KOKORO SETUP
# ============================================================
print("Loading Kokoro...")
from kokoro import KPipeline

pipeline = KPipeline(lang_code="a")
print("Kokoro loaded.\n\n")


# ============================
# AUDIO GENERATION
# ============================

cached_text = ""
character_voices = {}
#The fallback voice if no character voice is found
narrator_voice = characters.Character("am_adam", 1.0, 0.5)
gen_thread = None


class AudioSample:
    def __init__(self, audio, line, volume_multiplier):
        self.audio = audio
        self.line = line
        self.volume_multiplier = volume_multiplier

def generate_audio(readerUI, text, voice, line, speed, volume_multiplier):
    global generated_characters, audio_queue
    generator = pipeline(text, voice=voice, speed=speed)
    try:
        audio_chunks = []
        for _, _, audio in generator:
            if generation_stop.is_set():
                return
            audio_chunks.append(audio)
        audio_queue.append(AudioSample(audio_chunks, line, volume_multiplier))
    except Exception as e:
        print("Error generating audio for line:", line, voice, e)
        readerUI.log(f"ERROR! Could not generate audio for voice: {voice}")


def clamp(value, min_value, max_value):
    return max(min(value, max_value), min_value)

def get_character_voice(character):
    if character in character_voices:
        return character_voices[character]
    elif "NARRATOR" in character_voices:
        return character_voices["NARRATOR"]
    return narrator_voice

def queue_script_audio(readerUI, scriptLines):
    global character_voices, buffer_char_size
    for line in scriptLines:
        if generation_stop.is_set():
            print("Generation stopped.")
            readerUI.log("Generation stopped.")
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
            audio_queue.append(AudioSample(None, line, volume_multiplier))
        else:
            generate_audio(
                readerUI,
                line.text,
                character.voice,
                line,
                speed=speed,
                volume_multiplier=volume_multiplier,
            )

    # none to signal end
    audio_queue.append(None)


# ============================
# BUTTON ACTIONS
# ============================


def play(readerUI, text):
    global gen_thread, character_voices, cached_text, generation_lock

    with generation_lock:
        #only generate if text has changed or audio queue is empty
        should_generate = len(audio_queue) == 0 or (text != cached_text)

        start_playback(readerUI)

        if should_generate:  #Generate
            print("Generating... dialog mode:", readerUI.dialog_mode)
            cached_text = text
            set_audio_index(0)
        
            # Stop old generation if any
            generation_stop.set()

            if gen_thread and gen_thread.is_alive():
                print("Previous Generation hasn't finished yet...")

            # Clear old audio 

            audio_queue.clear()
            generation_stop.clear()
            character_voices = characters.load_characters(readerUI.dialog_mode)
            script_lines = []

            if(readerUI.dialog_mode):
                script_lines, new_text = scriptParsing.parse_script(text, character_voices)
                print(len(script_lines), "dialog lines parsed.")
            else:
                script_lines, new_text = scriptParsing.parse_text(text)
                print(len(script_lines), "reader lines parsed.")
                readerUI.set_script_contents(new_text)
            

            gen_thread = threading.Thread(
                target=queue_script_audio, args=(readerUI, script_lines), daemon=True
            )
            gen_thread.start()
            readerUI.set_status("Buffering")
            readerUI.log("Generating audio...")


def change_mode(readerUI, dialog_mode):
    global character_voices
    stop_playback(readerUI)




# ============================================================
# START APP
# ============================================================

app = ui.VoiceReaderUI(playRunnable=play, stopRunnable=stop_playback, pauseRunnable=pause_playback, seekRunnable=seek, modeChangeRunnable=change_mode)

def shutdown():
    print("Shutting down...")
    shutdown_playback(app)
    app.root.destroy()


app.root.protocol("WM_DELETE_WINDOW", shutdown)

# ============================
# PERMANENT PLAYBACK THREAD
# ============================
play_thread = threading.Thread(target=playback_thread, args=(app,), daemon=True)
play_thread.start()

app.run()
