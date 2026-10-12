<img src="icon/icon.png" alt="Voice Reader Icon" width=200></img>

# 🎙️ Voice Reader
Voice Reader is a Python-based UI application for reading screenplays and written content aloud using text-to-speech powered by [Kokoro](https://github.com/hexgrad/kokoro). 

Voice Reader supports two reading modes:

- **Dialog Mode** — Designed for screenplays and multi-character scripts with expressive voice control.
- **Reader Mode** — Designed for articles, stories, and single-voice narration.

## Features
- Screenplay-style dialog reading
- Dynamic reading speed controls
- Natural pauses and interruptions
- Single-voice narration mode
- Optional browser controls and browser audio playback

--------------

# Installation

1. Create a virtual environment
```bash
python3 -m venv .venv
```

2. Activate the environment
```bash
# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Run
```bash
python main.py
```


# Usage Modes

Voice Reader provides two modes:

## Dialog Mode

Dialog Mode is designed for screenplay-style content where different characters, emotions, pacing, and interruptions can be represented.

Lines can include special markers to adjust how they are spoken.

## Reader Mode

Reader Mode is intended for content that uses a single narrator voice. Recommended for Articles, Stories, Books, Documentation or Essays

Reader Mode ignores screenplay-style character changes and focuses on natural narration.


# Credit
(Icon by <a href="https://www.flaticon.com/free-icons/audio" ttle="audio icons"> Magnific </a>)
