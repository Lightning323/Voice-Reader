import ui
import threading
import scriptParsing
from playback import playback_thread, seek, start_playback, pause_playback, stop_playback, shutdown_playback,  audio_queue, generation_stop,generation_lock, set_audio_index
import characters
import time
from multiprocessing import Process
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
gen_threads = 0
latest_gen_id = 0 #Keep track of the last generation ID
gen_thread_lock = threading.Lock()
#The fallback voice if no character voice is found
narrator_voice = characters.Character("am_adam", 1.0, 0.5)
gen_thread = None


class AudioSample:
    def __init__(self, audio, line, volume_multiplier):
        self.audio = audio
        self.line = line
        self.volume_multiplier = volume_multiplier


def clamp(value, min_value, max_value):
    return max(min(value, max_value), min_value)

def get_character_voice(character):
    if character in character_voices:
        return character_voices[character]
    elif "NARRATOR" in character_voices:
        return character_voices["NARRATOR"]
    return narrator_voice

# ----------------------------
# AUDIO GENERATION
# ---------------------------

def generate_audio(my_gen_id, text, voice, speed):
    global generated_characters, audio_queue, gen_threads, latest_gen_id
    generator = pipeline(text, voice=voice, speed=speed)
    audio_chunks = []
    for _, _, audio in generator:
        if should_cancel_generation(my_gen_id):
            return
        audio_chunks.append(audio)

    return audio_chunks

def should_cancel_generation(my_gen_id):
    if generation_stop.is_set():
        return True
    with gen_thread_lock: #If we are another thread generating when a new thread starts, cancel this thread
        if my_gen_id != latest_gen_id:
            return True
    return False

def generate(readerUI, scriptLines):
    global character_voices, buffer_char_size, gen_threads, latest_gen_id
    cancel_generation(readerUI, max_iterations=60, delay=1) # We will wait up to 1 minute for generation to finish

    with gen_thread_lock:
        gen_threads += 1

        #Keep track of the latest thread. If other threads are still running, their ID will be lower than this
        latest_gen_id += 1
        my_gen_id = latest_gen_id

        audio_queue.clear()
        character_voices = characters.load_characters(readerUI.dialog_mode)
        generation_stop.clear() #If we are starting a new generation, clear the stop flag
        print("Generating audio... Generation threads:", gen_threads)
        set_audio_index(0)

    readerUI.set_status("Buffering")
    readerUI.log("Generating audio...")

    try:
        for line in scriptLines:
            if should_cancel_generation(my_gen_id):
                return

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
                if should_cancel_generation(my_gen_id):
                    return
                audio_queue.append(AudioSample(None, line, volume_multiplier))
            else: # Generate audio
                try:
                    audio_chunks = generate_audio(
                        my_gen_id,
                        text=line.text,
                        voice=character.voice,
                        speed=speed,
                    )
                    if should_cancel_generation(my_gen_id):
                        return
                    audio_queue.append(AudioSample(audio_chunks, line, volume_multiplier))
                except Exception as e:
                    readerUI.log(f"ERROR! Could not generate audio for voice: {character.voice}")
                    print("Error generating audio:", e)

        if not should_cancel_generation(my_gen_id):
            audio_queue.append(None)

    except Exception as e:
        print("Error generating audio:", e)
        readerUI.log(f"ERROR! Could not generate audio for line: {line}")
    finally:
        with gen_thread_lock:
            gen_threads -= 1
            print(f"Generation stopped for thread {my_gen_id}. Total threads:", gen_threads)
        readerUI.log("Generation stopped.")


# ============================
# BUTTON ACTIONS
# ============================


def cancel_generation(readerUI, max_iterations=5, delay=1, log=True):
    for i in range(0, max_iterations):
        if gen_threads > 0:
            if log:
                print("Previous Generation hasn't finished yet... gen threads:", gen_threads)
                readerUI.log("Previous Generation hasn't finished yet...")
                readerUI.set_status("Cancelling generation...")
            generation_stop.set()
            time.sleep(delay)
        else:
            break

def play(readerUI, text):
    global gen_thread, character_voices, cached_text, generation_lock, gen_threads

    with generation_lock:
        #only generate if text has changed or audio queue is empty
        should_generate = len(audio_queue) == 0 or (text != cached_text)

        if should_generate:  #Generate
            cancel_generation(readerUI, max_iterations=30, delay=0.01, log=False)  # We block here and in the thread itself, but we dont want to wait too long here because it will block the UI
            print("Preparing to Generating... dialog mode:", readerUI.dialog_mode, "gen threads:", gen_threads)

            if(readerUI.dialog_mode):
                script_lines, new_text = scriptParsing.parse_script(text, character_voices)
                print(len(script_lines), "dialog lines parsed.")
            else:
                script_lines, new_text = scriptParsing.parse_text(text)
                print(len(script_lines), "reader lines parsed.")
                readerUI.set_script_contents(new_text)

            #Make sure we get cached text EXACTLY as it is in the UI
            cached_text = readerUI.get_script_contents()

            gen_thread = threading.Thread(
                target=generate, args=(readerUI, script_lines), daemon=True
            )
            gen_thread.start()
            start_playback(readerUI)


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
