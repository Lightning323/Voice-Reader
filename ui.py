import tkinter as tk
from tkinter import ttk
import threading
import re

from character_editor import CharacterEditor

stop_flag = False
pause_flag = False


class ScreenplayPlayer:

    def __init__(self, playRunnable=None, stopRunnable=None):
        self.playRunnable = playRunnable
        self.stopRunnable = stopRunnable

        self.root = tk.Tk()
        self.root.title("Screenplay Player")
        self.root.geometry("1200x750")

        # -----------------------------
        # Toolbar
        # -----------------------------

        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill="x", padx=10, pady=10)

        ttk.Button(toolbar, text="▶ Play", command=self.play).pack(side="left", padx=5)
        # ttk.Button(toolbar, text="⏸ Pause", command=self.pause).pack(
        #     side="left", padx=5
        # )
        ttk.Button(toolbar, text="■ Stop", command=self.stop).pack(side="left", padx=5)

        ttk.Label(toolbar, text="Speed:").pack(side="left", padx=(30, 5))
        self.speed = tk.DoubleVar(value=0.9)
        ttk.Scale(toolbar, from_=0.5, to=2.5, variable=self.speed, length=250).pack(
            side="left", padx=5
        )


        ttk.Button(toolbar, text="Clear", command=self.clear_script).pack(side="left", padx=5)

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

        self.main_paned = ttk.PanedWindow(body, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill="both", expand=True)

        screenplay_frame = ttk.Frame(self.main_paned)
        right_panel = ttk.Frame(self.main_paned)

        self.main_paned.add(screenplay_frame, weight=3)
        self.main_paned.add(right_panel, weight=1)

        # ==========================================
        # Screenplay
        # ==========================================

        self.script = tk.Text(
            screenplay_frame,
            wrap="word",
            font=("Consolas", 12),
        )

        self.script.pack(fill="both", expand=True)

        self.script.tag_configure("gen", background="#dddddd", foreground="black")
        self.script.tag_configure("current", background="#ffd54f", foreground="black")
        self.script.tag_configure("character", foreground="#1565c0")
        self.script.tag_configure("narration", foreground="#555555")

        # ==========================================
        # Right vertical splitter
        # ==========================================

        self.right_paned = ttk.PanedWindow(right_panel, orient=tk.VERTICAL)
        self.right_paned.pack(fill="both", expand=True)

        # -----------------------------
        # Output log
        # -----------------------------

        output_frame = ttk.Frame(self.right_paned)

        self.output = tk.Text(
            output_frame,
            state="disabled",
            bg="#222",
            fg="white",
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
            self.right_paned.sashpos(0, max(150, right_height - 300))

        self.root.after(10, init_layout)

    # ========================================================
    # UI HELPERS
    # ========================================================

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

    def play(self):
        global stop_flag
        stop_flag = False
        text = self.script.get("1.0", "end")
        self.playRunnable(self, text)

    # def pause(self):
    #     global pause_flag
    #     pause_flag = not pause_flag

    def stop(self):
        global stop_flag
        stop_flag = True
        self.stopRunnable(self)

    def clear_script(self):
        self.script.delete("1.0", "end")

    # ========================================================
    # PARSER
    # ========================================================

    def run(self):
        self.root.mainloop()
