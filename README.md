<img src="icon/icon.png" alt="Voice Reader Icon" width=200></img>

# 🎙️ Voice Reader
Voice Reader is a desktop web UI for reading screenplays and written content aloud using text-to-speech powered by [Kokoro](https://github.com/hexgrad/kokoro). The window is provided by pywebview rather than a native widget toolkit.

Voice Reader supports two reading modes:

- **Dialog Mode** — Designed for screenplays and multi-character scripts with expressive voice control.
- **Reader Mode** — Designed for articles, stories, and single-voice narration.


## Features

- 🎭 Screenplay-style dialog reading
- 🎙️ Multiple character voices
- ⚡ Dynamic reading speed controls
- ⏸️ Natural pauses and interruptions
- 📖 Single-voice narration mode
- 🔊 Kokoro TTS integration
- 🌐 Optional browser controls and browser audio playback

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

On Linux, the requirements install pywebview's Qt browser backend as well. If
you previously installed only `pywebview`, rerun the command above so the Qt
backend is added.

For an X11 desktop on Ubuntu, Debian, or Zorin, install Qt's system windowing
dependency once before running the app:
```bash
sudo apt-get install libxcb-cursor0
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

## Web Interface

The desktop window loads directly from a local file and does **not** reserve a
port. This keeps the normal app free of port conflicts.

To let another device use the reader, choose a port in **Share with Other
Devices** and select **Allow devices & start**. The app displays a local-network
URL to open on a trusted device. Select **Stop sharing** when finished. While
sharing is running, generated audio is sent to the connected browser instead of
the computer speakers. The browser offers Play, Pause, Stop, Back, and Forward
controls and displays the current highlighted text and active voice.

The server is intended for a trusted local network. Stop it when it is no longer
needed.


# Character Voices
Voice Reader uses Kokoro voices. Available voices are grouped by language and gender.


## 🇺🇸 American Female (`af_*`)

| Voice | Description |
|---|---|
| `af_heart` | Warm, soft, emotional (default) |
| `af_bella` | Expressive and dynamic |
| `af_nicole` | Professional and clear |
| `af_jessica` | Friendly and conversational |
| `af_sarah` | Neutral and articulate |
| `af_sky` | Bright and energetic |
| `af_nova` | Slightly dreamy and gentle |
| `af_kore` | Soft and calm |
| `af_river` | Relaxed and flowing |
| `af_alloy` | Crisp and modern |
| `af_aoede` | Musical and lyrical |

---

## 🇺🇸 American Male (`am_*`)

| Voice | Description |
|---|---|
| `am_adam` | Deep narrator |
| `am_michael` | Natural and casual |
| `am_eric` | Clear and balanced |
| `am_liam` | Youthful |
| `am_echo` | Smooth |
| `am_onyx` | Deep tone |
| `am_fenrir` | Strong and dramatic |
| `am_puck` | Light and energetic |

---

## 🇬🇧 British Female (`bf_*`)

| Voice | Description |
|---|---|
| `bf_alice` | Clear, refined, neutral British accent |
| `bf_emma` | Warm, friendly, conversational |
| `bf_isabella` | Polished and expressive |
| `bf_lily` | Younger, bright, energetic |

---

## 🇬🇧 British Male (`bm_*`)

| Voice | Description |
|---|---|
| `bm_daniel` | Professional, neutral narrator |
| `bm_fable` | Dramatic and theatrical |
| `bm_george` | Relaxed and conversational |
| `bm_lewis` | Younger and approachable |


# Credit
(Icon by <a href="https://www.flaticon.com/free-icons/audio" ttle="audio icons"> Magnific </a>)
