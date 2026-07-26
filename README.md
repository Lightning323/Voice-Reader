# Screenplay Reader
A python base UI for reading screenplays.

## Influencing reading tone and speed

A few characters or markers in the screenplay can be used to change the reading tone or speed.

### Speed
Adding an indicator in parentheses can change the reading speed of that line.

* To make the line read faster, use `(_f_)` `(fast)`, `(frantic)`, or `(quick)`.

* To make the line slower, ise `(_s_)` `(slow)`, `(methodical)`, or `(thorough)`.

* You can increase or decrease even further by adding "very" `(very fast)`, `(very slow)`, etc, or `(_ff_)`, `(_ss_)`.
    * `(_fff_)`, `(_sss_)` for further increased speed, etc.

### Interruptions
Put a hyphen (`--` or `-`) at the end of a line to interrupt the line.

### Pauses
Put 2 or more dots (`. . .`, `…` or `...`) at the end of a line or on a newline to pause for a few seconds. The more dots, the longer the pause.

# CHARACTER VOICES
"""
🇺🇸 American Female (af_*)
| Voice |	Character |
|--------|-------------|
|af_heart | 	Warm, soft, emotional (default)
|af_bella | 	Expressive, dynamic, one of the best-rated
|af_nicole | 	Professional, clear
|af_jessica | 	Friendly, conversational
|af_sarah | 	Neutral, articulate
|af_sky | 	Bright, energetic
|af_nova | 	Slightly dreamy, gentle
|af_kore | 	Soft, calm
|af_river | 	Relaxed, flowing
|af_alloy | 	Crisp, modern
|af_aoede | 	Musical, lyrical

🇺🇸 American Male (am_*)
|Voice | 	Character|
|--------|-------------|
|am_adam | 	Deep narrator|
|am_michael | 	Natural, casual|
|am_eric | 	Clear, balanced|
|am_liam | 	Youthful|
|am_echo | 	Smooth|
|am_onyx | 	Deeper tone|
|am_fenrir | 	Strong, dramatic|
|am_puck | 	Lighter, energetic|

🇬🇧 British Female (bf_*)
bf_alice
bf_emma
bf_isabella
bf_lily

🇬🇧 British Male (bm_*)
bm_daniel
bm_fable
bm_george
bm_lewis