import tkinter as tk
from tkinter import ttk
import threading
import re

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

        ttk.Scale(toolbar, from_=0.5, to=1.5, variable=self.speed, length=150).pack(
            side="left", padx=5
        )

        self.status = ttk.Label(toolbar, text="Idle")

        self.status.pack(side="right", padx=10)

        # -----------------------------
        # Main area
        # -----------------------------

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        # screenplay

        self.script = tk.Text(body, wrap="word", font=("Consolas", 14))

        self.script.pack(side="left", fill="both", expand=True)

        # highlight styles
        self.script.tag_configure("gen", background="#eeeeee", foreground="black")
        self.script.tag_configure("current", background="#ffd54f", foreground="black")
        self.script.tag_configure("character", foreground="#1565c0")
        self.script.tag_configure("narration", foreground="#555555")

        # output

        self.output = tk.Text(
            body,
            width=35,
            state="disabled",
            bg="#222",
            fg="white",
            font=("Consolas", 11),
        )

        self.output.pack(side="right", fill="y")

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
            self.script.see(start)
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

    # ========================================================
    # PARSER
    # ========================================================



    def run(self):
        self.root.mainloop()