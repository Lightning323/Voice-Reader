# https://github.com/suno-ai/bark

from transformers import AutoProcessor, BarkModel
from IPython.display import Audio
"""
Male	v2/en_speaker_0, v2/en_speaker_2, v2/en_speaker_6
Female	v2/en_speaker_1, v2/en_speaker_3, v2/en_speaker_9
"""

"""
[laughter]
[laughs]
[sighs]
[music]
[gasps]
[clears throat]
— or ... for hesitations
♪ for song lyrics
CAPITALIZATION for emphasis of a word
[MAN] and [WOMAN] to bias Bark toward male and female speakers, respectively
"""


print("Loading model...")
processor = AutoProcessor.from_pretrained("suno/bark")
model = BarkModel.from_pretrained("suno/bark")
print("Model loaded.")

voice_preset = "v2/en_speaker_6"

inputs = processor("Hello, my dog is cute", voice_preset=voice_preset)

print("Generating...")
audio_array = model.generate(**inputs)
audio_array = audio_array.cpu().numpy().squeeze()

print("Playing...")
Audio(audio_array, rate=model.generation_config.sample_rate)