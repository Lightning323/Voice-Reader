"""Two-directional audio buffering for Voice Reader.

The generation logic lives here instead of in playback.py so the playback
worker can stay focused on playing lines. A single :class:`AudioBuffer` owns
the current script, the character voices, and two worker threads that grow the
queue in both directions around wherever playback is anchored.
"""

import threading
import time

import characters
from playback import (
    audio_queue,
    generation_stop,
    set_audio_index,
    prepend_sample,
    append_sample,
)


def clamp(value, min_value, max_value):
    return max(min(value, max_value), min_value)


class AudioSample:
    """One generated line of speech (or a pause, when ``audio`` is None)."""

    def __init__(self, audio, line, volume_multiplier, end_offset, script_index):
        self.audio = audio
        self.line = line
        self.volume_multiplier = volume_multiplier
        self.end_offset = end_offset
        self.script_index = script_index
        # The browser UI uses this to remove the item from its buffered text
        # when playback reaches it.
        self.web_item_id = None
        self.web_voice = ""


class AudioBuffer:
    """Generate audio around the current position in both directions.

    The playhead starts at the anchor line. The up worker prepends everything
    above it to the front of the queue, and the down worker appends the anchor
    and everything after it to the end. Prepending shifts the queue, so each
    front insertion advances the playhead index by one to keep it pointing at
    the same line.
    """

    def __init__(self):
        self.readerUI = None
        self._script_lines = []
        self._character_voices = {}
        self._load_pipeline = None
        self._lock = threading.RLock()
        self._gen_id = 0
        self._stop_event = threading.Event()
        self._threads = []
        self._done_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def begin(
        self,
        readerUI,
        script_lines,
        character_voices,
        load_pipeline,
        source_text,
        anchor_index=0,
    ):
        """Restart buffering from ``anchor_index`` after cancelling old workers."""
        self.readerUI = readerUI
        self._script_lines = list(script_lines)
        self._character_voices = character_voices
        self._load_pipeline = load_pipeline

        self._stop_workers()

        if not self._script_lines:
            with self._lock:
                audio_queue.clear()
                generation_stop.clear()
                set_audio_index(0)
            append_sample(None)
            return

        anchor_index = clamp(anchor_index, 0, len(self._script_lines) - 1)
        with self._lock:
            self._gen_id += 1
            gen_id = self._gen_id
            self._stop_event = threading.Event()
            stop_event = self._stop_event
            self._done_count = 0

            audio_queue.clear()
            generation_stop.clear()
            set_audio_index(0)

        readerUI.set_status("Buffering")
        readerUI.log("Generating audio...")
        readerUI.web_begin_buffering(source_text)

        self._threads = [
            threading.Thread(
                target=self._buffer_up,
                args=(gen_id, stop_event, anchor_index),
                name=f"voice-reader-buffer-up-{gen_id}",
                daemon=True,
            ),
            threading.Thread(
                target=self._buffer_down,
                args=(gen_id, stop_event, anchor_index),
                name=f"voice-reader-buffer-down-{gen_id}",
                daemon=True,
            ),
        ]
        for thread in self._threads:
            thread.start()

    # ------------------------------------------------------------------
    # Worker lifetime
    # ------------------------------------------------------------------

    def _stop_workers(self, join_timeout=1.0):
        with self._lock:
            self._stop_event.set()
            old_threads = list(self._threads)
            self._threads = []
        deadline = time.monotonic() + join_timeout
        for thread in old_threads:
            thread.join(max(0.0, deadline - time.monotonic()))

    def _is_cancelled(self, gen_id, stop_event):
        if stop_event.is_set():
            return True
        with self._lock:
            return self._gen_id != gen_id

    def _finish_worker(self, gen_id, stop_event):
        del stop_event
        with self._lock:
            if self._gen_id != gen_id:
                return
            self._done_count += 1
            if self._done_count >= 2:
                append_sample(None)
                self.readerUI.log("Generation stopped.")

    # ------------------------------------------------------------------
    # Workers
    # ------------------------------------------------------------------

    def _buffer_up(self, gen_id, stop_event, anchor_index):
        try:
            for script_index in range(anchor_index - 1, -1, -1):
                if self._is_cancelled(gen_id, stop_event):
                    return
                sample = self._generate_sample(gen_id, stop_event, script_index)
                if sample is None:
                    return
                prepend_sample(sample)
            self._finish_worker(gen_id, stop_event)
        except Exception as error:
            print("Up-buffer error:", error)

    def _buffer_down(self, gen_id, stop_event, anchor_index):
        try:
            for script_index in range(anchor_index, len(self._script_lines)):
                if self._is_cancelled(gen_id, stop_event):
                    return
                sample = self._generate_sample(
                    gen_id, stop_event, script_index, highlight=True
                )
                if sample is None:
                    return
                append_sample(sample)
            self._finish_worker(gen_id, stop_event)
        except Exception as error:
            print("Down-buffer error:", error)

    # ------------------------------------------------------------------
    # Line generation
    # ------------------------------------------------------------------

    def _generate_sample(self, gen_id, stop_event, script_index, highlight=False):
        line = self._script_lines[script_index]
        readerUI = self.readerUI

        if highlight:
            readerUI.highlight_gen(f"{line.start}.0", f"{line.end}.end")

        character = self._character_voice(line.character)
        speed = readerUI.speed.get() if readerUI else 1
        speed = clamp(
            speed * character.speed_multiplier * line.speed_multiplier, 0.05, 20
        )
        end_offset = line.end_offset / speed
        volume_multiplier = character.volume_multiplier

        audio_chunks = None
        if line.text.strip() != "":
            try:
                audio_chunks = self._generate_audio(
                    gen_id,
                    stop_event,
                    text=line.text,
                    voice=character.voice,
                    speed=speed,
                )
            except Exception as error:
                readerUI.log(
                    f"ERROR! Could not generate audio for voice: {character.voice}"
                )
                print("Error generating audio:", error)
            if audio_chunks is None:
                # Cancelled mid-generation; stop the worker without adding a line.
                return None

        if self._is_cancelled(gen_id, stop_event):
            return None

        sample = AudioSample(
            audio_chunks, line, volume_multiplier, end_offset, script_index
        )
        sample.web_item_id = readerUI.web_add_buffered_line(
            line.text, character.voice, line.start, line.end
        )
        sample.web_voice = character.voice
        return sample

    def _character_voice(self, character):
        if character in self._character_voices:
            return self._character_voices[character]
        if "NARRATOR" in self._character_voices:
            return self._character_voices["NARRATOR"]
        return characters.Character("am_adam", 1.0, 0.5)

    def _generate_audio(self, gen_id, stop_event, text, voice, speed):
        pipeline = self._load_pipeline()
        generator = pipeline(text, voice=voice, speed=speed)
        audio_chunks = []
        for _, _, audio in generator:
            if self._is_cancelled(gen_id, stop_event):
                return None
            audio_chunks.append(audio)
        return audio_chunks