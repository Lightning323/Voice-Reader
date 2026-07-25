
import pygame
import numpy as np
import time

pygame.mixer.init(
    frequency=24000,
    size=-16,
    channels=1
)

def play_audio(audio):
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
    delay = max(0, sound.get_length())
    sound.play()
    # print(delay)
    time.sleep(delay)