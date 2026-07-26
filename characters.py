import json
import os

class Character:
    def __init__(self, voice, speed_multiplier, volume_multiplier=0.5):
        self.voice = voice.lower().strip()
        self.speed_multiplier = speed_multiplier
        self.volume_multiplier = volume_multiplier


def load_characters(filename="characters.json"):
    if os.path.exists(filename):
        with open(filename, "r") as file:
            data = json.load(file)

        return {
            name: Character(
                info["voice"],
                info["speed_multiplier"],
                info["volume_multiplier"]
            )
            for name, info in data.items()
        }
    else:
        characters = {"NARRATOR":Character("am_adam", 1.0, 0.5)}
        save_characters(characters=characters)
        return characters

def save_characters(characters, filename="characters.json"):
    data = {}

    for name, character in characters.items():
        data[name] = {
            "voice": character.voice,
            "speed_multiplier": character.speed_multiplier,
            "volume_multiplier": character.volume_multiplier
        }

    with open(filename, "w") as file:
        json.dump(data, file, indent=4)