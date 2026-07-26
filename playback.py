
import pygame
import numpy as np
import time
# from pydub import AudioSegment
# from pydub.silence import detect_nonsilent

pygame.mixer.init(
    frequency=24000,
    size=-16,
    channels=1
)

def play_audio(audio_chunks, volume_multiplier, end_offset):
    if(audio_chunks is None): #Still play a pause
        time.sleep(max(1, 1+end_offset))
    else:
        for i, audio in enumerate(audio_chunks):
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
            sound.set_volume(max(0.0, min(1.0, volume_multiplier)))
            duration =sound.get_length() 

            sound.play()
            if i < len(audio_chunks) - 1:
                time.sleep(duration)
            else: # ... adjust time offset only at final wait.
                time.sleep(max(0.01, duration + end_offset))