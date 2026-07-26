import queue
import threading
import scriptParsing

script = """
PATEL
But what about--

CARTER
We dont have time for this! . . . 

ELANA
The information has come from 2,160,000 light years away. 
The signal was picked up as a distortion of gravitational waves. 
Numerous outposts informed us of strange anomalies in gravitational fields. 
Most of the information was gathered from reconnaissance stations. After sufficient data and analysis can confirm with high certainty that there is intelligent life in sector SDSS J1426.

RAMIREZ
(fast, Shouting over the noise) Is the ship supposed to make this noise?

. . .

CARTER
SDSS J1426 is a dead pocket. A stable star system tucked inside a dark matter void is mathematically impossible. How can you be certain of the origin?


"""
class Character:
    def __init__(self, voice, speed_multiplier):
        self.voice = voice
        self.speed_multiplier = speed_multiplier


CHARACTER_VOICES = {
    "RAMIREZ": Character("af_aoede", 1),
    "PATEL": Character("am_eric", 1),
    "CARTER": Character("am_michael", 1),
    "ELANA": Character("af_nicole", 1),
}

scriptLines = scriptParsing.parse_script(script, CHARACTER_VOICES)
for line in scriptLines:
    print(line,"\n")