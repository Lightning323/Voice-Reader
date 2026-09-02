import pygame
import numpy as np
import time
import threading

_mixer_initialized = False
_mixer_lock = threading.Lock()


def _ensure_mixer_initialized():
    """Delay local-audio setup so headless browser playback needs no device."""
    global _mixer_initialized
    with _mixer_lock:
        if not _mixer_initialized:
            pygame.mixer.init(frequency=24000, size=-16, channels=1)
            _mixer_initialized = True


current_channel = None
playback_index = 0
playing_index = 0
audio_queue = []

# For the generator
generation_stop = threading.Event()
generation_lock = threading.Lock()

play_event = threading.Event()  # Playback allowed
allow_playback = True  # For preventing race condition

shutdown_event = threading.Event()  # App closing
playback_state_lock = threading.Lock()


# Utils
def set_audio_index(index):
    global playback_index, audio_queue
    playback_index = clamp(index, 0, len(audio_queue) - 1)


def clamp(value, min_value, max_value):
    return max(min(value, max_value), min_value)


def interrupt_audio():
    global current_channel, allow_playback
    if current_channel:
        current_channel.stop()
        allow_playback = False


# Exported
def shutdown_playback(readerUI):
    global shutdown_event
    shutdown_event.set()
    start_playback(readerUI)


# START =========================================================
def start_playback(readerUI):
    global allow_playback, playback_state_lock
    with playback_state_lock:
        allow_playback = True
        play_event.set()
        # The remote player must have one long-lived media source before the
        # playback worker begins publishing PCM.  Mobile browsers can suspend
        # page JavaScript in the background, but continue consuming an active
        # HTML media stream.
        readerUI.web_prepare_audio_stream()

    print("Started")
    readerUI.playback_mode(True)
    readerUI.set_status("Playing")


# PAUSE =========================================================
def pause_playback(readerUI):
    global playback_index, playback_state_lock, allow_playback, playing_index

    with playback_state_lock:
        if allow_playback and playing_index == playback_index:  # If not pausing, than seek back
            playback_index = clamp(playback_index - 1, 0, len(audio_queue) - 1)
        play_event.clear()
        allow_playback = False
        interrupt_audio()  # Set playback to false THAN interrupt (Interrupt last)
        readerUI.web_interrupt_audio()

    print("Paused")
    readerUI.playback_mode(False)
    readerUI.set_status("Paused")


# STOP =========================================================
def stop_playback(readerUI):
    global gen_thread, playback_index, playback_state_lock, cached_text, allow_playback

    pause_playback(readerUI)
    
    with playback_state_lock:
        playback_index = 0
        audio_queue.clear()  # Clear audio cache
        cached_text = ""
        generation_stop.set()  # Stop generating

    readerUI.web_clear_playback()

    print("Stopped")
    readerUI.set_status("Stopped")


def finish_playback(readerUI):
    """Finish naturally without cutting off buffered browser audio."""
    global playback_index, playback_state_lock, cached_text, allow_playback

    with playback_state_lock:
        play_event.clear()
        allow_playback = False
        playback_index = 0
        audio_queue.clear()
        cached_text = ""
        generation_stop.set()

    # Closing the stream tells the browser where the media ends, but lets it
    # play the final buffered seconds instead of treating completion as Pause.
    readerUI.web_finish_audio_stream()
    readerUI.playback_mode(False)
    readerUI.set_status("Stopped")


# SEEK =========================================================
def seek(readerUI, seekVector):
    global playback_index, audio_queue, playback_state_lock

    # with playback_state_lock:
    #     interrupt_audio()
    #     start_playback(readerUI)

    readerUI.set_status("Skipping " + ("forward" if seekVector == 1 else "backward"))
    playback_index += seekVector
    set_audio_index(playback_index)

    if playback_index < len(audio_queue):
        sample = audio_queue[playback_index]
        if sample is not None:
            readerUI.highlight_seek(f"{sample.line.start}.0", f"{sample.line.end}.end")
            readerUI.web_seek_line(sample.line.start, sample.line.end)


def playback_thread(readerUI):
    global play_event, shutdown_event, audio_queue, playback_index, playback_state_lock, allow_playback, playing_index

    while not shutdown_event.is_set():
        try:
            play_event.wait()  # Wait until Play is pressed

            if(generation_stop.is_set()): #Dont play if generation is stopped
                time.sleep(0.1)
                continue

            # If the buffer is incomplete and there are less than N samples
            if len(audio_queue) < 50 and (
                len(audio_queue) == 0 or audio_queue[-1] is not None
            ):
                play_after_n_chars = 75
                if(readerUI.dialog_mode):
                    play_after_n_chars = 175

                is_buffer_large_enough = False
                buffer_char_size = 0  # calculate buffer char size
                for sample in audio_queue:
                    buffer_char_size += len(sample.line.text)
                    if buffer_char_size > play_after_n_chars:
                        is_buffer_large_enough = True
                        break

                if not is_buffer_large_enough:
                    readerUI.set_status(
                        f"Buffering {round(buffer_char_size / play_after_n_chars * 100)}%"
                    )
                    time.sleep(0.5)
                    continue

            if allow_playback:

                if playback_index >= len(audio_queue):
                    continue
                sample = audio_queue[playback_index]
                playback_index += 1

                # End marker
                if sample is None:
                    finish_playback(readerUI)
                    continue

                if readerUI:
                    readerUI.highlight_seek(
                        f"{sample.line.start}.0", f"{sample.line.end}.end"
                    )
                    readerUI.highlight_playback(
                        f"{sample.line.start}.0", f"{sample.line.end}.end"
                    )
                    speed_info = ""
                    if sample.line.speed_multiplier != 1:
                        speed_info = f"({sample.line.speed_multiplier:.2f}x) "
                    readerUI.log(f'{sample.line.character}: {speed_info}"{sample.line.text}"')
                    readerUI.set_status(f"{sample.line.character}")
                    readerUI.web_start_line(
                        sample.web_item_id,
                        sample.line.text,
                        sample.web_voice,
                        sample.line.start,
                        sample.line.end,
                    )
                #print("Playing... ", playback_index, sample.line, sample.volume_multiplier)
                playing_index = playback_index
                interrupted = play_audio(
                    readerUI,
                    sample.audio,
                    volume_multiplier=sample.volume_multiplier,
                    end_offset=sample.end_offset,
                )
                if interrupted:  # Pause it ourself
                    print("Interrupted")
                    pause_playback(readerUI)

        except Exception as e:
            print("Playback thread error", e)

    print("Playback thread exited")


"""
Returns true if interrupted
"""


def play_audio(readerUI, audio_chunks, volume_multiplier, end_offset):
    global current_channel

    if readerUI and readerUI.is_web_audio_active():
        return play_web_audio(readerUI, audio_chunks, volume_multiplier, end_offset)

    if audio_chunks is None:  # Still play a pause
        if delay_unless_interrupted(None, (max(1, 1 + end_offset))):
            return True
    else:
        _ensure_mixer_initialized()
        for i, audio in enumerate(audio_chunks):
            audio = audio.detach().cpu().numpy().flatten()

            audio = np.clip(audio * 32767, -32768, 32767).astype(np.int16)

            sound = pygame.mixer.Sound(buffer=audio.tobytes())
            sound.set_volume(max(0.0, min(1.0, volume_multiplier)))
            duration = sound.get_length()

            # print(f"Sound {i} duration: {duration}")
            current_channel = sound.play()
            if delay_unless_interrupted(current_channel, duration):
                return True
            if i == len(audio_chunks) - 1 and delay_unless_interrupted(
                None, max(0.01, end_offset)
            ):
                return True

    return False


def play_web_audio(readerUI, audio_chunks, volume_multiplier, end_offset):
    """Append one line to the browser's persistent PCM media stream.

    The old per-clip acknowledgement protocol relied on JavaScript running at
    every clip boundary.  That is exactly the work mobile browsers may defer
    while the page is backgrounded.  The playback worker now supplies timing;
    the browser only has to keep consuming its one active media resource.
    """
    if audio_chunks is None:
        duration = max(1, 1 + end_offset)
        if not readerUI.web_stream_audio(b"\0\0" * round(duration * 24000)):
            return True
        return delay_unless_interrupted(None, duration)

    pcm_parts = []
    duration = 0.0
    for audio in audio_chunks:
        pcm = np.clip(
            audio.detach().cpu().numpy().flatten() * volume_multiplier * 32767,
            -32768,
            32767,
        ).astype(np.int16)
        pcm_parts.append(pcm.tobytes())
        duration += len(pcm) / 24000

    # Preserve pauses as PCM silence so the browser never reaches the end of a
    # media resource between spoken lines.  A negative interruption offset
    # intentionally has no added pause, matching desktop playback.
    pause_duration = max(0.01, end_offset)
    pcm_parts.append(b"\0\0" * round(pause_duration * 24000))
    if not readerUI.web_stream_audio(b"".join(pcm_parts)):
        return True
    return delay_unless_interrupted(None, duration + pause_duration)

"""
Returns True if interrupted
"""
def delay_unless_interrupted(channel, duration):
    global playback_id

    start = time.monotonic()
    channel_started = channel is None
    while time.monotonic() - start < duration:
        if allow_playback is False:
            return True
        if channel is not None:
            if channel.get_busy():
                channel_started = True
            elif channel_started:
                return False
        time.sleep(0.01)

    # The duration is only a fallback for a channel that never started. Once
    # the mixer has begun the clip, wait for its real end before advancing.
    while channel is not None and channel_started and channel.get_busy():
        if allow_playback is False:
            return True
        time.sleep(0.01)
    return False


def get_non_silent_duration(audio, sample_rate=24000):
    threshold = 500

    for i in range(len(audio) - 1, -1, -1):
        if abs(audio[i]) > threshold:
            return (i + 1) / sample_rate

    return 0
