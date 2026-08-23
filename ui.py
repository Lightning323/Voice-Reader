import tkinter as tk
import ttkbootstrap as ttk
import os
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
        webServerRunnable=None,
    ):
        self.advanced_mode = not os.path.exists("simple-mode.txt")
        self.playRunnable = playRunnable
        self.stopRunnable = stopRunnable
        self.pauseRunnable = pauseRunnable
        self.seekRunnable = seekRunnable
        self.modeChangeRunnable = modeChangeRunnable
        self.webServerRunnable = webServerRunnable
        # Attached by main.py after it creates the web server controller.
        self.web_server = None

        self.root = ttk.Window()
        self.root.title("Voice Reader")
        self.root.geometry("1200x750")
        # icon_path = os.path.join(os.path.dirname(__file__), "icon", "icon.png")
        # print("icon path:", icon_path)
        icon = tk.PhotoImage(file="icon/icon.png")
        self.root.iconphoto(True, icon)

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

        self.selected_mode = tk.StringVar(value="Reader Mode")
        self.dialog_mode = False

        self.mode_dropdown = ttk.Combobox(
            toolbar,
            textvariable=self.selected_mode,
            values=["Dialog Mode", "Reader Mode"],
            state="readonly",  # Prevents typing custom values
        )
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
        editor_frame.pack(fill="both", expand=True, padx=0, pady=0)

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
            padx=100,
            pady=10,
            spacing1=2,
            spacing3=4,
            font=("Consolas", self.script_font_size),
        )
        self.script.pack(side="left", fill="both", expand=True)

        self.script.tag_configure(
            "reader_margin",
            lmargin1=20,
            lmargin2=20,
            rmargin=20
        )
        self.script.tag_configure("page_margin",
            lmargin1=160,
            lmargin2=160,
            rmargin=160
        )
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

        # -----------------------------
        # IMPORT Dialog
        # -----------------------------
        self.import_frame = ttk.Frame(right_panel, height=80)
        self.import_frame.pack_propagate(False)   # Don't let children change the height
        self.import_frame.grid_propagate(False)   # (Optional, harmless if you only use pack)

        ttk.Label(
            self.import_frame,
            text="Import Text",
            font=("", 10, "bold"),
        ).pack(side="top", anchor="w", padx=5, pady=(0, 8))
        ttk.Button(
            self.import_frame,
            text="Paste All",
            command=self.clear_and_paste,
        ).pack(fill="x", padx=5, pady=5)
        self.import_frame.pack(fill="both", expand=False, padx=10)

        # -----------------------------
        # WEB INTERFACE
        # -----------------------------
        self.web_server_frame = ttk.Frame(right_panel, height=122)
        self.web_server_frame.pack_propagate(False)
        self.web_server_frame.grid_propagate(False)

        ttk.Label(
            self.web_server_frame,
            text="Web Interface",
            font=("", 10, "bold"),
        ).pack(side="top", anchor="w", padx=5, pady=(8, 4))

        web_controls = ttk.Frame(self.web_server_frame)
        web_controls.pack(fill="x", padx=5)
        ttk.Label(web_controls, text="Port").pack(side="left", padx=(0, 6))
        self.web_port = tk.StringVar(value="8765")
        self.web_port_selector = ttk.Combobox(
            web_controls,
            textvariable=self.web_port,
            values=("8765", "8080", "5000"),
            width=8,
        )
        self.web_port_selector.pack(side="left")
        self.web_server_button = ttk.Button(
            web_controls,
            text="Start Server",
            command=self.toggle_web_server,
        )
        self.web_server_button.pack(side="right")
        self.web_server_status = ttk.Label(
            self.web_server_frame,
            text="Start a local server to use Voice Reader from a browser.",
            wraplength=290,
            justify="left",
        )
        self.web_server_status.pack(fill="x", padx=5, pady=(7, 0))
        self.web_server_frame.pack(fill="x", expand=False, padx=10, pady=(8, 4))

        # ==========================================
        # Right vertical splitter
        # ==========================================
        self.right_paned = ttk.Panedwindow(right_panel, orient=tk.VERTICAL)
        self.right_paned.pack(fill="both", expand=True, padx=10)
        # -----------------------------
        # Output log
        # -----------------------------

        
        output_frame = ttk.Frame(self.right_paned)

        self.log_label = ttk.Label(
            output_frame, text="Log", font=("", 10, "bold")
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

        # if(self.advanced_mode):
        self.right_paned.add(output_frame, weight=0)
        self.right_paned.add(character_frame, weight=1)

        self._last_dark = darkdetect.isDark()
        self.root.after(1000, self.check_theme)
        self.apply_theme(darkdetect.isDark())
        self.change_mode()
        # ==========================================
        # Initial splitter positions
        # ==========================================

        def init_layout():
            self.root.update_idletasks()

            # Right panel starts at ~340px wide
            window_width = self.root.winfo_width()
            self.main_paned.sashpos(0, window_width - 340)

            # Character editor takes up the remaining space
            right_height = self.right_paned.winfo_height()

            self.right_paned.sashpos(0, 0)
            # self.right_paned.sashpos(0, 100) #Set 2nd parameter to any finite value to scale the output log, or set to 0 to hide it

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

    def set_script_contents(self, text, set_margin=True):
        self.script.delete("1.0", "end")
        self.script.insert("1.0", text)

        if set_margin:
            self.script.tag_add("page_margin", "1.0", "end")

        if self.web_server and self.web_server.is_running:
            self.web_server.update_state(text=text)

    def get_script_contents(self):
        return self.script.get("1.0", "end-1c")

    def change_font_size(self, event, delta=0):
        if (event and event.delta > 0) or delta > 0:
            self.script_font_size += 1
        else:
            self.script_font_size = max(8, self.script_font_size - 1)
        self.script.configure(font=("Consolas", self.script_font_size))
        return "break"

    def ui(self, fn):

        self.root.after(0, fn)

    """
    start, end are the line markers
    """
    def highlight_playback(self, start, end):
        def update():
            self.script.tag_remove("current", "1.0", "end")
            self.script.tag_add("current", start, end)
            self.script.see(end)
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
            self.script.see(end)

        self.ui(update)

    def playback_mode(self, isPlaybackMode):
        if isPlaybackMode:
            self.mode_dropdown.config(state="disabled")
        else:
            self.mode_dropdown.config(state="readonly")

    def log(self, text):
        print(text)
        def update():
            self.output.config(state="normal")
            self.output.insert("end", text + "\n\n")
            self.output.see("end")
            self.output.config(state="disabled")

        self.ui(update)

    def set_status(self, text):
        if self.web_server and self.web_server.is_running:
            self.web_server.update_state(status=text)
        self.ui(lambda: self.status.config(text=text))

    # ========================================================
    # WEB PLAYBACK BRIDGE
    # ========================================================

    def is_web_audio_active(self):
        return bool(self.web_server and self.web_server.is_running)

    def web_begin_buffering(self, text):
        if self.is_web_audio_active():
            self.web_server.begin_buffering(text)

    def web_add_buffered_line(self, text, voice, start_line, end_line):
        if self.is_web_audio_active():
            return self.web_server.add_buffered_line(
                text, voice, start_line, end_line
            )
        return None

    def web_start_line(self, item_id, text, voice, start_line, end_line):
        if self.is_web_audio_active():
            self.web_server.start_line(
                item_id, text, voice, start_line, end_line
            )

    def web_send_audio(self, pcm, duration, volume):
        if self.is_web_audio_active():
            return self.web_server.publish_wav(pcm, duration, volume)
        return False

    def web_interrupt_audio(self):
        if self.is_web_audio_active():
            self.web_server.interrupt_audio()

    def web_clear_playback(self):
        if self.is_web_audio_active():
            self.web_server.clear_playback()

    def toggle_web_server(self):
        if not self.webServerRunnable:
            self.set_web_server_status(False, "Web interface is unavailable.")
            return

        try:
            port = int(self.web_port.get())
        except ValueError:
            self.set_web_server_status(False, "Enter a valid port number.")
            return

        success, message, running = self.webServerRunnable(self, port)
        self.set_web_server_status(running, message)
        if not success:
            return

    def set_web_server_status(self, running, message):
        self.web_server_button.config(text="Stop Server" if running else "Start Server")
        self.web_port_selector.config(state="disabled" if running else "normal")
        self.web_server_status.config(text=message)

    # ========================================================
    # CONTROLS
    # ========================================================

    def change_mode(self, event=None):
        self.dialog_mode = self.mode_dropdown.get() == "Dialog Mode"
        self.character_editor.set_dialog_mode(self.dialog_mode)
        self.modeChangeRunnable(self, self.dialog_mode)
        print("DIALOG MODE:", self.dialog_mode)

    def play(self):
        global stop_flag
        stop_flag = False
        text = self.get_script_contents()
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
    # TEXT IMPORT
    # ========================================================

    def clear_and_paste(self):
        self.script.delete("1.0", "end")
        self.script.insert("1.0", self.script.clipboard_get())

    # ========================================================
    # PARSER
    # ========================================================

    def run(self):
        self.root.mainloop()
