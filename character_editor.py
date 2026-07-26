import tkinter as tk
from tkinter import ttk
from characters import load_characters, save_characters, Character


class CharacterEditor(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        self.characters = load_characters()
        self.selected_character = None

        # Character list
        self.character_list = tk.Listbox(self, width=20)
        self.character_list.grid(row=0, column=0, rowspan=5, padx=5, pady=5)

        for name in self.characters:
            self.character_list.insert(tk.END, name)

        self.character_list.bind(
            "<<ListboxSelect>>",
            self.load_character
        )

        # Fields
        ttk.Label(self, text="Name").grid(row=0, column=1)
        self.name_entry = ttk.Entry(self)
        self.name_entry.grid(row=0, column=2)

        ttk.Label(self, text="Voice").grid(row=1, column=1)
        self.voice_entry = ttk.Entry(self)
        self.voice_entry.grid(row=1, column=2)

        ttk.Label(self, text="Speed").grid(row=2, column=1)
        self.speed_entry = ttk.Entry(self)
        self.speed_entry.grid(row=2, column=2)

        ttk.Label(self, text="Volume").grid(row=3, column=1)
        self.volume_entry = ttk.Entry(self)
        self.volume_entry.grid(row=3, column=2)

        # Buttons
        ttk.Button(
            self,
            text="Add Character",
            command=self.add_character
        ).grid(row=4, column=1)

        ttk.Button(
            self,
            text="Save Changes",
            command=self.save_character
        ).grid(row=4, column=2)

        ttk.Button(
            self,
            text="Save JSON",
            command=lambda: save_characters(self.characters)
        ).grid(row=5, column=2)


    def load_character(self, event=None):
        selection = self.character_list.curselection()

        if not selection:
            return

        name = self.character_list.get(selection[0])
        self.selected_character = name

        character = self.characters[name]

        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, name)

        self.voice_entry.delete(0, tk.END)
        self.voice_entry.insert(0, character.voice)

        self.speed_entry.delete(0, tk.END)
        self.speed_entry.insert(0, character.speed_multiplier)

        self.volume_entry.delete(0, tk.END)
        self.volume_entry.insert(0, character.volume_multiplier)


    def save_character(self):
        if self.selected_character is None:
            return

        character = self.characters[self.selected_character]

        character.voice = self.voice_entry.get()
        character.speed_multiplier = float(self.speed_entry.get())
        character.volume_multiplier = float(self.volume_entry.get())


    def add_character(self):
        name = "NEW_CHARACTER"

        counter = 1
        while name in self.characters:
            name = f"NEW_CHARACTER_{counter}"
            counter += 1

        self.characters[name] = Character(
            "af_heart",
            1.0,
            0.5
        )

        self.character_list.insert(
            tk.END,
            name
        )