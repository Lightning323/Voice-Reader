import tkinter as tk
import ttkbootstrap as ttk
import tkinter as tk
import threading
import re
import darkdetect

from character_editor import CharacterEditor

stop_flag = False
pause_flag = False


class VoiceReaderUI:

    def __init__(
        self,
        playRunnable=None,
        stopRunnable=None,
        pauseRunnable=None,
        seekRunnable=None,
        modeChangeRunnable=None,
    ):
        self.playRunnable = playRunnable
        self.stopRunnable = stopRunnable
        self.pauseRunnable = pauseRunnable
        self.seekRunnable = seekRunnable
        self.modeChangeRunnable = modeChangeRunnable

        self.root = ttk.Window()
        self.root.title("Voice Reader")
        self.root.geometry("1200x750")

        # -----------------------------
        # Toolbar
        # -----------------------------

        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill="x", padx=10, pady=10)

        ttk.Button(toolbar, text="▶ Play", command=self.play).pack(side="left", padx=5)
        ttk.Button(toolbar, text="⏸ Pause", command=self.pause).pack(
            side="left", padx=5
        )
        ttk.Button(toolbar, text="<<", command=self.seek_back).pack(side="left", padx=5)
        ttk.Button(toolbar, text=">>", command=self.seek_forward).pack(
            side="left", padx=5
        )
        ttk.Button(toolbar, text="■ Stop", command=self.stop).pack(side="left", padx=5)

        ttk.Label(toolbar, text="Speed:").pack(side="left", padx=(30, 5))
        self.speed = tk.DoubleVar(value=0.9)
        ttk.Scale(
            toolbar,
            from_=0.4,
            to=2.5,
            variable=self.speed,
            length=250,
            command=self.set_speed,
        ).pack(side="left", padx=5)
        self.speed_dial = ttk.Label(toolbar, text="1x").pack(side="left", padx=(10, 5))

        self.selected_mode = tk.StringVar(value="Dialog Mode")
        self.mode_dropdown = ttk.Combobox(
            toolbar,
            textvariable=self.selected_mode,
            values=["Dialog Mode", "Reader Mode"],
            state="readonly",  # Prevents typing custom values
        )
        self.dialog_mode = True
        self.mode_dropdown.pack(pady=20, side="right")
        self.mode_dropdown.bind("<<ComboboxSelected>>", self.change_mode)
        self.playback_mode(False)

        self.status = ttk.Label(toolbar, text="Idle")

        self.status.pack(side="right", padx=10)

        # -----------------------------
        # Main area
        # -----------------------------

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        # ==========================================
        # Main horizontal splitter
        # ==========================================

        self.main_paned = ttk.Panedwindow(body, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill="both", expand=True)

        screenplay_frame = ttk.Frame(self.main_paned)
        right_panel = ttk.Frame(self.main_paned)

        self.main_paned.add(screenplay_frame, weight=3)
        self.main_paned.add(right_panel, weight=1)
        # ==========================================
        # Screenplay Editor
        # ==========================================

        # Editor container
        editor_frame = ttk.Frame(screenplay_frame)
        editor_frame.pack(fill="both", expand=True)

        # Search Bar =================================
        self.search_frame = ttk.Frame(editor_frame)
        self.search_entry = ttk.Entry(self.search_frame, width=40)
        self.search_entry.pack(side="left", padx=5, pady=5, fill="x", expand=True)
        self.search_button = ttk.Button(
            self.search_frame, text="Find", command=self.search_text
        )
        self.search_button.pack(side="left", padx=5)
        ttk.Button(self.search_frame, text="X", command=self.hide_search).pack(
            side="right", padx=5
        )
        self.search_frame.pack_forget()

        # ==========================================
        # Screenplay Editor
        # ==========================================

        text_frame = ttk.Frame(editor_frame)
        text_frame.pack(fill="both", expand=True)
        self.script_font_size = 12

        self.script = tk.Text(
            text_frame,
            bg="#141414",
            fg="#d4d4d4",
            insertbackground="white",
            selectbackground="#264f78",
            wrap="word",
            undo=True,
            maxundo=-1,
            padx=10,
            pady=10,
            spacing1=2,
            spacing3=4,
            font=("Consolas", self.script_font_size),
        )
        self.script.pack(side="left", fill="both", expand=True)

        self.script.tag_configure("gen", background="#404040", foreground="white")
        self.script.tag_configure("seek", background="#005bb5", foreground="black")
        self.script.tag_configure("current", background="#b58900", foreground="black")
        # self.script.tag_configure("character", foreground="#4fc3f7")
        # self.script.tag_configure("narration", foreground="#bbbbbb")
        self.script.bind("<Control-z>", lambda e: (self.script.edit_undo(), "break"))
        self.script.bind("<Control-y>", lambda e: (self.script.edit_redo(), "break"))
        self.script.bind(
            "<Control-a>", lambda e: (self.script.tag_add("sel", "1.0", "end"), "break")
        )
        self.script.bind("<Control-f>", lambda e: self.show_search())

        # ==========================================
        # Font Size Controls
        # ==========================================
        self.script.bind("<Control-MouseWheel>", self.change_font_size)
        # Linux mouse support
        self.script.bind("<Control-Button-4>", lambda e: self.change_font_size(None, 1))
        self.script.bind(
            "<Control-Button-5>", lambda e: self.change_font_size(None, -1)
        )
        # ==========================================
        # Right vertical splitter
        # ==========================================
        self.right_paned = ttk.Panedwindow(right_panel, orient=tk.VERTICAL)
        self.right_paned.pack(fill="both", expand=True)

        # -----------------------------
        # Output log
        # -----------------------------

        output_frame = ttk.Frame(self.right_paned)

        self.log_label = ttk.Label(
            output_frame, text="Information", font=("", 10, "bold")
        )
        self.log_label.pack(side="top", anchor="w", padx=5, pady=(0, 8))
        self.output = tk.Text(
            output_frame,
            state="disabled",
            font=("Consolas", 11),
        )

        self.output.pack(fill="both", expand=True)

        # -----------------------------
        # Character editor
        # -----------------------------

        character_frame = ttk.Frame(self.right_paned)

        self.character_editor = CharacterEditor(character_frame)
        self.character_editor.pack(fill="both", expand=True)

        self.right_paned.add(output_frame, weight=1)
        self.right_paned.add(character_frame, weight=1)

        self._last_dark = darkdetect.isDark()
        self.root.after(1000, self.check_theme)
        self.apply_theme(darkdetect.isDark())
        # ==========================================
        # Initial splitter positions
        # ==========================================

        def init_layout():
            self.root.update_idletasks()

            # Right panel starts at ~340px wide
            window_width = self.root.winfo_width()
            self.main_paned.sashpos(0, window_width - 340)

            # Character editor starts at ~300px tall
            right_height = self.right_paned.winfo_height()
            self.right_paned.sashpos(0, max(150, right_height - 400))

        self.root.after(10, init_layout)

    # ==========================================

    def check_theme(self):
        dark = darkdetect.isDark()
        if dark != self._last_dark:
            self._last_dark = dark
            self.apply_theme(dark)

        self.root.after(1000, self.check_theme)

    def apply_theme(self, dark):
        self.root.style.theme_use("darkly" if dark else "flatly")
        self.character_editor.set_theme(dark)
        if dark:
            self.script.config(
                bg="#141414",
                fg="#d4d4d4",
                selectbackground="#264f78",
                insertbackground="white",
            )
            self.script.tag_configure("gen", background="#404040", foreground="white")
            self.script.tag_configure("seek", background="#005bb5", foreground="white")
            self.script.tag_configure(
                "current", background="#b58900", foreground="white"
            )
        else:
            self.script.config(
                bg="white",
                fg="black",
                selectbackground="#63a1e0",
                insertbackground="black",
            )
            self.script.tag_configure("gen", background="#DEDEDE", foreground="black")
            self.script.tag_configure("seek", background="#44a1ff", foreground="black")
            self.script.tag_configure(
                "current", background="#ffbf00", foreground="black"
            )

    # ========================================================
    # UI HELPERS
    # ========================================================

    def show_search(self):
        self.search_frame.pack(fill="x", before=self.script.master)
        self.search_entry.focus()
        self.search_entry.bind("<Return>", lambda e: self.search_text())
        self.search_entry.bind("<Escape>", lambda e: self.hide_search())

    def hide_search(self):
        self.search_frame.pack_forget()
        self.script.tag_remove("seek", "1.0", "end")

    def search_text(self):
        query = self.search_entry.get()
        if not query:
            return

        self.script.tag_remove("seek", "1.0", "end")
        index = self.script.search(query, "1.0", stopindex="end")

        if index:
            end = f"{index}+{len(query)}c"
            self.script.tag_add("seek", index, end)
            self.script.see(index)

    def change_font_size(self, event, delta=0):
        if (event and event.delta > 0) or delta > 0:
            self.script_font_size += 1
        else:
            self.script_font_size = max(8, self.script_font_size - 1)
        self.script.configure(font=("Consolas", self.script_font_size))
        return "break"

    def ui(self, fn):

        self.root.after(0, fn)

    def highlight_playback(self, start, end):
        def update():
            self.script.tag_remove("current", "1.0", "end")
            self.script.tag_add("current", start, end)
            self.script.see(start)

        self.ui(update)

    def highlight_gen(self, start, end):
        def update():
            self.script.tag_remove("gen", "1.0", "end")
            self.script.tag_add("gen", start, end)

        self.ui(update)

    def highlight_seek(self, start, end):
        def update():
            self.script.tag_remove("seek", "1.0", "end")
            self.script.tag_add("seek", start, end)
            self.script.see(start)

        self.ui(update)

    def playback_mode(self, isPlaybackMode):
        if isPlaybackMode:
            self.mode_dropdown.config(state="disabled")
        else:
            self.mode_dropdown.config(state="normal")

    def log(self, text):
        def update():
            self.output.config(state="normal")
            self.output.insert("end", text + "\n\n")
            self.output.see("end")
            self.output.config(state="disabled")

        self.ui(update)

    def set_status(self, text):
        self.ui(lambda: self.status.config(text=text))

    # ========================================================
    # CONTROLS
    # ========================================================

    def change_mode(self, event):
        self.dialog_mode = self.mode_dropdown.get() == "Dialog Mode"
        self.character_editor.set_dialog_mode(self.dialog_mode)
        self.modeChangeRunnable(self, self.dialog_mode)
        print("DIALOG MODE:", self.dialog_mode)

    def play(self):
        global stop_flag
        stop_flag = False
        text = self.script.get("1.0", "end")
        self.playRunnable(self, text)

    def pause(self):
        global pause_flag
        self.pauseRunnable(self)

    def seek_back(self):
        self.seekRunnable(self, -1)

    def seek_forward(self):
        self.seekRunnable(self, 1)

    def stop(self):
        global stop_flag
        stop_flag = True
        self.stopRunnable(self)

    def set_speed(self, value):
        try:
            num_val = float(value)
            self.speed_dial.config(text=f"{num_val:.2f}x")
        except ValueError:
            self.speed_dial.config(text=f"{value}x")

    # ========================================================
    # PARSER
    # ========================================================

    def run(self):
        self.root.mainloop()
