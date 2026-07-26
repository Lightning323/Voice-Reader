import tkinter as tk
from tkinter import ttk
from characters import load_characters, save_characters, Character


class CharacterEditor(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.characters = load_characters()
        self.selected_character = None

        # Layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1) 
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=0)

        # ==================================================
        # Character List
        # ==================================================

        ttk.Label(
            self,
            text="Characters",
            font=("", 10, "bold")
        ).grid(row=0, column=0, sticky="w", padx=5, pady=(5, 2))

        # Frame gives the listbox a minimum height
        list_frame = ttk.Frame(self, height=200)
        list_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=5,
            pady=(0, 5),
        )

        # Prevent the frame from shrinking below 200px
        list_frame.grid_propagate(False)

        self.character_list = tk.Listbox(
            list_frame,
            bg="#2b2b2b",
            fg="#ffffff",
            selectbackground="#0d6efd",
            selectforeground="#ffffff",
            highlightthickness=0,
            borderwidth=0,
            activestyle="none",
        )
        self.character_list.pack(fill="both", expand=True)


        for name in self.characters:
            self.character_list.insert(tk.END, name)

        self.character_list.bind(
            "<<ListboxSelect>>",
            self.load_character
        )

        # ==================================================
        # Buttons
        # ==================================================

        button_frame = ttk.Frame(self)
        button_frame.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=5,
            pady=(0, 8)
        )

        button_frame.columnconfigure((0, 1), weight=1)

        ttk.Button(
            button_frame,
            text="Add",
            command=self.add_character
        ).grid(row=0, column=0, sticky="ew", padx=(0, 2))

        ttk.Button(
            button_frame,
            text="Delete",
            command=self.delete_character
        ).grid(row=0, column=1, sticky="ew", padx=(2, 0))

        # ==================================================
        # Properties
        # ==================================================

        properties = ttk.LabelFrame(self, text="Properties")
        properties.grid(
            row=3,
            column=0,
            sticky="nsew",
            padx=5,
            pady=(0, 5)
        )

        properties.columnconfigure(1, weight=1)
        properties.rowconfigure(0, weight=1)
        properties.rowconfigure(1, weight=1)
        properties.rowconfigure(2, weight=1)
        properties.rowconfigure(3, weight=1)

        # Name
        ttk.Label(properties, text="Name").grid(
            row=0,
            column=0,
            sticky="w",
            padx=5,
            pady=3
        )

        self.name_entry = ttk.Entry(properties)
        self.name_entry.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=5,
            pady=3
        )

        # Voice
        ttk.Label(properties, text="Voice").grid(
            row=1,
            column=0,
            sticky="w",
            padx=5,
            pady=3
        )

        self.voice_entry = ttk.Entry(properties)
        self.voice_entry.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=5,
            pady=3
        )

        # Speed
        ttk.Label(properties, text="Speed").grid(
            row=2,
            column=0,
            sticky="w",
            padx=5,
            pady=3
        )

        self.speed_entry = ttk.Entry(properties)
        self.speed_entry.grid(
            row=2,
            column=1,
            sticky="ew",
            padx=5,
            pady=3
        )

        # Volume
        ttk.Label(properties, text="Volume").grid(
            row=3,
            column=0,
            sticky="w",
            padx=5,
            pady=3
        )

        self.volume_entry = ttk.Entry(properties)
        self.volume_entry.grid(
            row=3,
            column=1,
            sticky="ew",
            padx=5,
            pady=3
        )

        # ==================================================
        # Auto-save
        # ==================================================

        for widget in (
            self.name_entry,
            self.voice_entry,
            self.speed_entry,
            self.volume_entry,
        ):
            widget.bind("<FocusOut>", self.auto_save)
            widget.bind("<Return>", self.auto_save)

    def normalize_float(self, value, min_value, max_value):
        try:
            value = float(value)
            return max(min(value, max_value), min_value)
        except ValueError:
            return min_value


    def normalize_name(self, event=None):
        value = self.name_entry.get().strip().upper()

        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, value)


    def normalize_voice(self, event=None):
        value = self.voice_entry.get().strip().lower()

        self.voice_entry.delete(0, tk.END)
        self.voice_entry.insert(0, value)


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

        self.character_list.delete(0, tk.END)

        for name in self.characters:
            self.character_list.insert(tk.END, name)

        index = list(self.characters.keys()).index(name)

        self.character_list.selection_clear(0, tk.END)
        self.character_list.selection_set(index)
        self.character_list.event_generate("<<ListboxSelect>>")

        save_characters(self.characters)

    def auto_save(self, event=None):
        if self.selected_character is None:
            return

        # Normalize text
        self.normalize_name()
        self.normalize_voice()

        old_name = self.selected_character
        new_name = self.name_entry.get().strip()

        if not new_name:
            return

        character = self.characters[old_name]

        character.voice = self.voice_entry.get()
        character.speed_multiplier = self.normalize_float(self.speed_entry.get(), 0.1, 100.0)
        character.volume_multiplier = self.normalize_float(self.volume_entry.get(), 0.0, 1.0)


        # Rename
        if new_name != old_name:

            # Prevent overwriting another character
            if new_name in self.characters:
                return

            self.characters[new_name] = character
            del self.characters[old_name]

            self.selected_character = new_name

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