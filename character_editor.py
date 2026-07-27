import tkinter as tk
from tkinter import ttk
from characters import load_characters, save_characters, Character
import utils
import regex as re

voice_options = [
    # 🇺🇸 American Female
    "af_heart",
    "af_bella",
    "af_nicole",
    "af_jessica",
    "af_sarah",
    "af_sky",
    "af_nova",
    "af_kore",
    "af_river",
    "af_alloy",
    "af_aoede",
    # 🇺🇸 American Male
    "am_adam",
    "am_michael",
    "am_eric",
    "am_liam",
    "am_echo",
    "am_onyx",
    "am_fenrir",
    "am_puck",
    # 🇬🇧 British Female
    "bf_alice",
    "bf_emma",
    "bf_isabella",
    "bf_lily",
    # 🇬🇧 British Male
    "bm_daniel",
    "bm_fable",
    "bm_george",
    "bm_lewis",
]

class CharacterEditor(ttk.Frame):

    def __init__(self, parent):
        super().__init__(parent)
        self.dialog_mode = True

        # Layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=0)

        # ==================================================
        # Character List
        # ==================================================

        self.menu_label = ttk.Label(self, text="Characters", font=("", 10, "bold"))
        self.menu_label.grid(row=0, column=0, sticky="w", padx=5, pady=(5, 2))

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
            highlightthickness=0,
            borderwidth=0,
            activestyle="none",
        )
        self.character_list.pack(fill="both", expand=True)

        self.character_list.bind("<<ListboxSelect>>", self.select_character_from_list)

        # ==================================================
        # Buttons
        # ==================================================

        self.button_frame = ttk.Frame(self)

        self.button_frame.columnconfigure((0, 1), weight=1)

        ttk.Button(self.button_frame, text="Add", command=self.add_character).grid(
            row=0, column=0, sticky="ew", padx=(0, 2)
        )

        ttk.Button(
            self.button_frame, text="Delete", command=self.delete_character
        ).grid(row=0, column=1, sticky="ew", padx=(2, 0))

        # ==================================================
        # Properties
        # ==================================================

        properties = ttk.LabelFrame(self, text="Properties")
        properties.grid(row=3, column=0, sticky="nsew", padx=5, pady=(0, 5))

        properties.columnconfigure(1, weight=1)
        properties.rowconfigure(0, weight=1)
        properties.rowconfigure(1, weight=1)
        properties.rowconfigure(2, weight=1)
        properties.rowconfigure(3, weight=1)

        # Name
        self.name_label = ttk.Label(properties, text="Name")

        self.name_entry = ttk.Entry(properties)

        # Voice
        ttk.Label(properties, text="Voice").grid(
            row=1, column=0, sticky="w", padx=5, pady=3
        )

        

        self.voice_entry = ttk.Combobox(
            properties, state="readonly", values=voice_options
        )

        self.voice_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=3)

        # Speed
        ttk.Label(properties, text="Speed").grid(
            row=2, column=0, sticky="w", padx=5, pady=3
        )

        self.speed_entry = ttk.Entry(properties)
        self.speed_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=3)

        # Volume
        ttk.Label(properties, text="Volume").grid(
            row=3, column=0, sticky="w", padx=5, pady=3
        )

        self.volume_entry = ttk.Entry(properties)
        self.volume_entry.grid(row=3, column=1, sticky="ew", padx=5, pady=3)

        self.set_dialog_mode(self.dialog_mode)

        # ==================================================
        # Auto-save
        # ==================================================

        self.name_entry.bind("<Return>", self.rename_character)
        self.speed_entry.bind("<KeyRelease>", self.update_character)
        self.volume_entry.bind("<KeyRelease>", self.update_character)
        self.voice_entry.bind("<<ComboboxSelected>>", self.update_character)

    def set_theme(self, dark_mode):
        if dark_mode:
            self.character_list.configure(bg="#2b2b2b", fg="#ffffff", selectbackground="#0d6efd",  selectforeground="#ffffff")
        else:
            self.character_list.configure(borderwidth=0, bg="#e7e7e7", fg="#000000", selectbackground="#90bcff",  selectforeground="#000000")

    def set_dialog_mode(self, dialog_mode):
        self.selected_character = None
        self.dialog_mode = dialog_mode
        if self.dialog_mode:
            self.menu_label.config(text="Character Voices")
            self.button_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=(0, 8))
            self.name_entry.config(state="normal")
            self.name_label.grid(row=0, column=0, sticky="w", padx=5, pady=3)
            self.name_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=3)
        else:
            self.menu_label.config(text="Reader Voice")
            self.button_frame.grid_forget()
            self.name_label.grid_forget()
            self.name_entry.grid_forget()
            self.name_entry.config(state="disabled")

        self.characters = load_characters(dialog_mode)
        self.populate_character_list()

    def select_character_from_list(self, event=None):
        selection = self.character_list.curselection()
        if not selection:
            return
        name = self.character_list.get(selection[0])
        self.selected_character = name

        # populate fields
        character = self.characters[self.selected_character]
        name = self.selected_character.strip().upper()
        voice = character.voice
        speed_multiplier = character.speed_multiplier
        volume_multiplier = character.volume_multiplier

        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, name)

        self.voice_entry.set(voice)

        self.speed_entry.delete(0, tk.END)
        self.speed_entry.insert(0, speed_multiplier)

        self.volume_entry.delete(0, tk.END)
        self.volume_entry.insert(0, volume_multiplier)

    def populate_character_list(self):
        self.character_list.delete(0, tk.END)

        for name in self.characters:
            self.character_list.insert(tk.END, name)

        if not self.characters:
            self.selected_character = None
            return
        
        if self.selected_character not in self.characters:
            self.selected_character = next(iter(self.characters))

        index = list(self.characters).index(self.selected_character)
        self.character_list.selection_set(index)
        self.character_list.event_generate("<<ListboxSelect>>")
        
    def delete_character(self):
        if self.selected_character is None or not self.dialog_mode: # Only set name if in dialog mode
            return

        name = self.selected_character
        del self.characters[name]
        
        self.populate_character_list()

        save_characters(self.characters, self.dialog_mode)

    def update_character(self, event=None):
        if self.selected_character is None:
            return
        
        character = self.characters[self.selected_character]
        character.voice = self.voice_entry.get()
        character.speed_multiplier = utils.normalize_float(self.speed_entry.get(), 0.1, 100.0)
        character.volume_multiplier = utils.normalize_float(self.volume_entry.get(), 0.0, 1.0)
        save_characters(self.characters, self.dialog_mode)

    def rename_character(self, event=None):
        if self.selected_character is None or not self.dialog_mode: # Only set name if in dialog mode
            return

        old_name = self.selected_character
        new_name = self.name_entry.get().strip().upper()
        #replace all whitespace with just a single space
        new_name = re.sub(r'\s+', ' ', new_name)

        if not new_name:
            return

        character = self.characters[old_name]

        # Rename
        if new_name != old_name:
            # Prevent overwriting another character
            if new_name in self.characters:
                return
            self.characters[new_name] = character
            del self.characters[old_name]
            self.selected_character = new_name
            self.populate_character_list()

            save_characters(self.characters, self.dialog_mode)

    def add_character(self):
        name = "NEW_CHARACTER"
        counter = 1
        while name in self.characters:
            name = f"NEW_CHARACTER_{counter}"
            counter += 1

        self.characters[name] = Character("af_heart", 1.0, 0.5)

        self.selected_character = name
        self.populate_character_list()

        save_characters(self.characters, self.dialog_mode)
