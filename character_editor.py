import tkinter as tk
from tkinter import ttk
from characters import load_characters, save_characters, Character


class CharacterEditor(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.columnconfigure(2, weight=1)
        self.characters = load_characters()
        self.selected_character = None

        # Character list
        self.character_list = tk.Listbox(self)
        self.character_list.grid(row=0, column=0, rowspan=5, padx=3, pady=3)

        for name in self.characters:
            self.character_list.insert(tk.END, name)

        self.character_list.bind(
            "<<ListboxSelect>>",
            self.load_character
        )

        # Fields
        ttk.Label(self, text="Name").grid(row=0, column=1)
        self.name_entry = ttk.Entry(self)
        self.name_entry.grid(row=0, column=2, padx=3, pady=3)

        ttk.Label(self, text="Voice").grid(row=1, column=1)
        self.voice_entry = ttk.Entry(self)
        self.voice_entry.grid(row=1, column=2, padx=3, pady=3)

        ttk.Label(self, text="Speed").grid(row=2, column=1)
        self.speed_entry = ttk.Entry(self)
        self.speed_entry.grid(row=2, column=2, padx=3, pady=3)

        ttk.Label(self, text="Volume").grid(row=3, column=1)
        self.volume_entry = ttk.Entry(self)
        self.volume_entry.grid(row=3, column=2, padx=3, pady=3)

        #save events
        self.name_entry = ttk.Entry(self)
        self.name_entry.grid(row=0, column=2)

        self.voice_entry = ttk.Entry(self)
        self.voice_entry.grid(row=1, column=2)

        self.speed_entry = ttk.Entry(self)
        self.speed_entry.grid(row=2, column=2)

        self.volume_entry = ttk.Entry(self)
        self.volume_entry.grid(row=3, column=2)

        self.name_entry.bind("<FocusOut>", self.auto_save)
        self.voice_entry.bind("<FocusOut>", self.auto_save)
        self.speed_entry.bind("<FocusOut>", self.auto_save)
        self.volume_entry.bind("<FocusOut>", self.auto_save)

        # Buttons
        ttk.Button(
            self,
            text="Add Character",
            command=self.add_character
        ).grid(row=4, column=1, padx=3, pady=3)

        ttk.Button(
            self,
            text="Delete Character",
            command=self.delete_character
        ).grid(row=4, column=2, padx=3, pady=3)



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

    def delete_character(self):
        if self.selected_character is None:
            return

        name = self.selected_character

        del self.characters[name]

        # Refresh list
        self.character_list.delete(0, tk.END)

        for character_name in self.characters:
            self.character_list.insert(tk.END, character_name)

        # Clear fields
        self.selected_character = None

        self.name_entry.delete(0, tk.END)
        self.voice_entry.delete(0, tk.END)
        self.speed_entry.delete(0, tk.END)
        self.volume_entry.delete(0, tk.END)

        save_characters(self.characters)

    def auto_save(self, event=None):
        if self.selected_character is None:
            return

        old_name = self.selected_character
        new_name = self.name_entry.get().strip()

        if not new_name:
            return

        character = self.characters[old_name]

        character.voice = self.voice_entry.get()

        try:
            character.speed_multiplier = float(self.speed_entry.get())
            character.volume_multiplier = float(self.volume_entry.get())
        except ValueError:
            return

        # Handle rename
        if new_name != old_name:
            self.characters[new_name] = character
            del self.characters[old_name]
            self.selected_character = new_name

            self.character_list.delete(0, tk.END)

            for name in self.characters:
                self.character_list.insert(tk.END, name)

            index = list(self.characters.keys()).index(new_name)
            self.character_list.selection_set(index)

        save_characters(self.characters)


    def save_character(self):
        if self.selected_character is None:
            return

        old_name = self.selected_character
        new_name = self.name_entry.get().strip()

        if not new_name:
            return

        character = self.characters[old_name]

        # Update values
        character.voice = self.voice_entry.get()
        character.speed_multiplier = float(self.speed_entry.get())
        character.volume_multiplier = float(self.volume_entry.get())

        # Rename character
        if new_name != old_name:
            self.characters[new_name] = character
            del self.characters[old_name]

            self.selected_character = new_name

            # Refresh list
            self.character_list.delete(0, tk.END)
            for name in self.characters:
                self.character_list.insert(tk.END, name)

            index = list(self.characters.keys()).index(new_name)
            self.character_list.selection_set(index)

        save_characters(self.characters)


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

        # Select new character
        index = self.character_list.size() - 1
        self.character_list.selection_clear(0, tk.END)
        self.character_list.selection_set(index)
        self.character_list.event_generate("<<ListboxSelect>>")
        save_characters(self.characters)