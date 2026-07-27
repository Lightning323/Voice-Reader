import json
import os

class Character:
    def __init__(self, voice, speed_multiplier, volume_multiplier=0.5):
        self.voice = voice.lower().strip()
        self.speed_multiplier = speed_multiplier
        self.volume_multiplier = volume_multiplier

    def __repr__(self):
        return f"Character(voice={self.voice}, speed_multiplier={self.speed_multiplier}, volume_multiplier={self.volume_multiplier})"

def get_file(dialog_mode):
    if dialog_mode:
        return os.path.join(os.getcwd(), "dialog_characters.json")
    else:
        return os.path.join(os.getcwd(), "reader_characters.json")

def load_characters(dialog_mode):
    filename = get_file(dialog_mode)
    print("Loading characters from", os.path.abspath(filename))

    if os.path.exists(filename):
        with open(filename, "r") as file:
            data = json.load(file)
        return {
            name: Character(**info)
            for name, info in data.items()
        }

    print("Saving default characters...")
    characters = {"NARRATOR": Character("am_adam", 1.0, 0.5)}
    save_characters(characters, dialog_mode)
    return characters

def save_characters(characters, dialog_mode):
    print("Saving characters...")
    filename = get_file(dialog_mode)

    data = {
        name: character.__dict__
        for name, character in characters.items()
    }

    with open(filename, "w") as file:
        json.dump(data, file, indent=4)