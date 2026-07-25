import queue
import threading
import scriptParsing

script = """
INT. COCKPIT - HYPERSPACE / DARK MATTER POCKET
The smooth, blue streaks of stars, painting a tunnel have vanished. Outside the hull, the view is a violent, churning soup of pitch-black voids and jagged streaks of light.

	PATEL
I’ve never seen space like this before, This is surreal, … And you said you’ve seen everything.

CARTER
-- I've seen a lot, but this… nevermind. It’s a straight shot from here. We will be arriving in 2 weeks, 4 days.

After 2 weeks of traveling in darkness, the ship begins violently shuddering. Alarms blare in a discordant chorus. Overhead structural beams groan under immense, unnatural pressure.

RAMIREZ is strained against her harness, desperately typing on a console that keeps flickering. PATEL grips the flight yoke with white knuckles, fighting the ship's drift.

RAMIREZ
(Shouting over the noise)
Is the ship supposed to make this noise?

CARTER
These ships are supposed to handle a degree of strong gravitational force.

PATEL
Captain, We’re losing stabilization in the starboard nacelle. Sensor readings indicate dark matter density is three hundred percent higher than ground control predicted!

RAMIREZ
This can't be a black hole, can it.? O.R.I.O.N, Trajectory plan!!

CARTER
-- Cancel it O.R.I.O.N!! Keep your eyes on your instruments! -- There’s no event horizon in sight…

CARTER
We can’t rely on your navigational programming anymore, You need to pilot the pulse drives.

CARTER sits in the command chair, his face illuminated by a sea of flashing amber and red warning lights. He looks calm, but his grip on his armrests is tight enough to rip the fabric.

CARTER
Keep her straight, Patel. If we drop out of the corridor now, the displacement will turn us into space dust!

(navigation is murky, Its pitch black, no landmarkings)

	PATEL
How can I fly straight without my instruments?!

A massive jolt rocks the ship. A conduit behind Ramirez sparks violently, filling the back of the cockpit with acrid gray smoke. She coughs, swatting the smoke away while rerouting power.

RAMIREZ
Hull integrity at sixty-four percent and dropping! Captain, the navigational computer can't lock onto the relativity clock—the dark matter is scrambling the quantum sync! We’re flying blind!

PATEL
I’ve got total engine pitch-lock! She’s not responding to manual override!
Outside, a massive wave of dark energy slams into the ship. A terrible, metallic screech echoes through the hull as a piece of external shielding tears away into the void.

RAMIREZ
(Panic creeping in)
We're losing the main thrusters! We're breaking apart.

CARTER
(Leaning forward, authoritative)
Not on my watch. Ramirez, dump the auxiliary fuel into the primary manifold! Give him the thrust he needs!

RAMIREZ
If I override the safety limits, the boosters will melt!

CARTER
Do it! Now!

Ramirez slams her palm against a protected red toggle on her console.
The engine roar changes from a high-pitched whine to a deep, guttural thrum that vibrates through the characters' teeth. The ship surges forward, trembling so violently that the cockpit glass begins to spiderweb with tiny fractures.

PATEL
(Straining)
Ten seconds to pocket exit! Hold on!

The flashing alarms merge into a single, continuous scream. The violent shaking reaches an absolute crescendo—and then, suddenly…

EXT. UNKNOWN PLANET - CONTINUOUS
SNAP.
The chaotic violet static instantly vanishes. The ship drops out of FTL travel with a violent lurch, dead-stick and drifting.

The silence is deafening.

PATEL
W-what happened, Did we make it?

CARTER
Do we have communication again? Star fleet, do you copy?

No response, only static.

PATEL
Interference is still too strong sir.


After 4 hours, light appears in the tunnel once again, On the spectrometer display spins a massive, eerie, galaxy shrouded in dark, swirling atmospheric storms. The ship is a total mess—trailing a cloud of frozen coolant, sparks spitting from its underbelly, its hull scorched black.


INT. COCKPIT - CONTINUOUS
The heavy shuddering stops, replaced by the low, dying hum of failing backup systems. The crew slumps forward in their seats, gasping for air.

Patel slowly lets go of the flight yoke. His hands are visibly shaking.

PATEL
(Whispering)
We're out. We made it.


Ramirez looks up at her console, wiping a streak of soot from her forehead.

RAMIREZ
Define "made it." Main power is dead. Life support is on batteries. And Captain?
She looks out the main viewscreen at the looming planet below.

RAMIREZ
The navigational computer is completely fried. I don't think we have a way home.
Carter unbuckles his harness, standing up stiffly. He looks out at the dark red tunnel.

CARTER
One problem at a time, It seems as though the worst is over, Lets keep our ship running at minimum capacity, I want every ounce of energy conserved for the duration of the journey.

	PATEL
We don't know if the other spacecraft made it, We may be the only o--

CARTER
We haven't lost them! We’ll just have to be patient until signal integrity is recovered.

	PATEL
Captain?

	CARTER
What.

PATEL
Don't ask why, but I might need a bag…


EXT. DEEP SPACE - THE EDGE OF THE SYSTEM - CONTINUOUS
The FTL tunnel completely dissolves. The frantic, warping streaks of light snap back into fixed, brilliant points of starlight.
Ahead of the fleet sits a massive, ominous celestial view: a dying, crimson Red Dwarf Star. Orbiting it are thick, jagged rings of shattered planetary debris and dense asteroid belts—all warping under heavy local gravity.

INT. COCKPIT - CONTINUOUS
The primary console monitors slowly flicker back to life, painting the crew’s faces in crisp blue data streams.

PATEL
(Exhaling deeply)
Real space. Actual, genuine real space. I've never been so happy to see a starfield in my life.

RAMIREZ
Don't celebrate yet, Patel. Look at the telemetry.
Ramirez taps her screen, pulling up a shifting wave-grid displaying massive spikes in gravitational energy.

RAMIREZ
The gravitational shear in this system is completely off the charts. The dark matter pocket didn't just isolate this place—it’s compressing it. O.R.I.O.N., do you copy now?
A smooth, synthesized electronic voice chimes through the overhead speakers.
O.R.I.O.N.

System diagnostics operational. Quantum sync restored. Warning: Extreme gravitational fluctuations detected ahead.



CARTER
(Into comms)


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