import re


def map_range(value, in_min, in_max, out_min, out_max):
    return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min


class ScriptLine:
    def __init__(self, text, character, speed_multiplier, end_offset, start, end):
        self.text = text.strip()
        self.character = character

        # Should we subtract N seconds or add N seconds to the audio file?
        self.end_offset = end_offset
        # How fast should we speak this line
        self.speed_multiplier = speed_multiplier

        # Line start and end
        self.start = start
        self.end = end

    def __str__(self):
        return f'{self.character}: "{self.text}" (offset={self.end_offset}; x{self.speed_multiplier}) ({self.start}-{self.end})'


# ---------------------
# DIOLOGUE PARSING
# ---------------------


def add_script_line(script_lines, speech, character, start, end):

    speech = speech.strip()
    speed_multiplier, speech = calculate_speed_multiplier(speech)
    end_offset = calculate_end_offset(speech, speed_multiplier)

    speech = format_line(speech)

    script_lines.append(
        ScriptLine(speech, character, speed_multiplier, end_offset, start, end)
    )


SPEED_PATTERNS = [
    (1.75, ["fff-", "fff_", "(fff)"], 
     ["_fff_", "-fff-", "very very fast", "very very rapid", "very very frantic", "very very quick"]),

    (1.45, ["ff-", "ff_", "(ff)"], 
     ["_ff_", "-ff-", "very fast", "very rapid", "very frantic", "very quick"]),

    (1.28, ["f-", "f_", "(f)"],
     ["_f_", "-f-", "fast", "rapid", "frantic", "quick"]),

    (0.5, ["sss-", "sss_", "(sss)"],
     ["_sss_", "-sss-", "very very slow", "very very methodical", "very very thorough"]),

    (0.53, ["ss-", "ss_", "(ss)"],
     ["_ss_", "-ss-", "very slow", "very methodical", "very thorough"]),

    (0.75, ["s-", "s_", "(s)"],
     ["_s_", "-s-", "slow", "methodical", "thorough"]),

]

def calculate_speed_multiplier(speech):
    #preformat the text so we can better recognize patterns
    formatted_text = " ".join(speech.replace(",", "").replace(".", "").split())

    for multiplier, starts_with, words_in_parentheses in SPEED_PATTERNS:
        for prefix in starts_with:
            if speech.startswith(prefix):
                return multiplier, speech[len(prefix):].lstrip()

        if in_parentheses(formatted_text, words_in_parentheses):
            return multiplier, speech

    return 1.0, speech


def in_parentheses(text, words):
    notes = " ".join(re.findall(r"\((.*?)\)", text))
    return any(word in notes for word in words)



def calculate_end_offset(speech, speed_multiplier):
    # Interruption / pause adjustment
    speech = speech.replace("…", "...").replace(". . .", "...").replace("—", "-")
    space_removal = speech.replace(" ", "")
    trailing_dots = len(space_removal) - len(space_removal.rstrip("."))
    trailing_dashes = len(space_removal) - len(space_removal.rstrip("-"))

    # More dots = longer pauses, more dashes = more abrupt interruptions
    if trailing_dashes >= 1:
        end_offset = map_range(
            min(3, trailing_dashes),
            1,
            2,
            -0.35 / speed_multiplier,
            -1.0 / speed_multiplier,
        )
    elif trailing_dots >= 2:
        end_offset = map_range(
            min(6, trailing_dots), 2, 6, 1 / speed_multiplier, 5 / speed_multiplier
        )
    else:
        end_offset = 0

    return end_offset


def parse_script(text, character_voices):
    script_lines = []
    # Get the lines

    lines = text.splitlines()

    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        line_character_formatted = line.upper().replace(":", "").strip()
        if line_character_formatted in character_voices:  # CHARACTER
            character = line_character_formatted
            i += 1
            while i < len(lines) and lines[i].strip():
                dialogue = lines[i].strip()
                add_script_line(script_lines, dialogue, character, i + 1, i + 1)
                i += 1

        else:  # If we dont have a character, it must be NARRATION
            while (
                i < len(lines)
                and lines[i].strip()
                and lines[i].upper() not in character_voices
            ):
                dialogue = lines[i].strip()
                add_script_line(script_lines, dialogue, "NARRATOR", i + 1, i + 1)
                i += 1

    return script_lines





def format_line(text, remove_parentheses=True):
    text = text.replace("…", "...").replace(". . .", "...").replace("—", "-")

    if remove_parentheses:
        text = re.sub(r"\([^)]*\)", "", text)

    # Get rid of double spaces
    text = re.sub(r"\s+", " ", text)

    # Get rid of dots or dashes if thats all there is
    if text and all(c in ".- " for c in text):
        text = ""

    return text


# ---------------------
# MONOLOGE
# ---------------------


def parse_text(text):
    lines = text.splitlines()
    script_lines = []
    for i, line in enumerate(lines):
        line = line.strip()
        if line:

            speed_multiplier = 1.0  # calculate_speed_multiplier(line)
            end_offset = calculate_end_offset(line, speed_multiplier)

            line = format_line(line)

            script_line = ScriptLine(
                line, "NARRATOR", speed_multiplier, end_offset, i + 1, i + 1
            )

            script_lines.append(script_line)
    return script_lines
