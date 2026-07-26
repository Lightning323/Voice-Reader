import json


class Character:
    def __init__(self, voice, speed_multiplier, volume_multiplier=0.5):
        self.voice = voice
        self.speed_multiplier = speed_multiplier
        self.volume_multiplier = volume_multiplier


def load_characters(filename="characters.json"):
    try:
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
    except FileNotFoundError:
        return {}

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