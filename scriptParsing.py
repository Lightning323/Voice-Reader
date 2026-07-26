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


def add_script_line(script_lines, speech, character, start, end):
    end_offset = 0
    speed_multiplier = 1
    speech = speech.strip()

    # Speed adjustment
    fast_format = " ".join(speech.replace(",", "").replace(".", "").split())
    # Fast
    if in_parentheses(
        fast_format,
        [
            "_fff_",
            "very very fast",
            "very very rapid",
            "very very frantic",
            "very very quick",
        ],
    ):
        speed_multiplier = 1.6
    elif in_parentheses(
        fast_format, ["_ff_", "very fast", "very rapid", "very frantic", "very quick"]
    ):
        speed_multiplier = 1.4
    elif in_parentheses(fast_format, ["_f_", "fast", "rapid", "frantic", "quick"]):
        speed_multiplier = 1.28
    # Slow
    elif in_parentheses(
        fast_format,
        ["_sss_", "very very slow", "very very methodical", "very very thorough"],
    ):
        speed_multiplier = 0.45
    elif in_parentheses(
        fast_format, ["_ss_", "very slow", "very methodical", "very thorough"]
    ):
        speed_multiplier = 0.52
    elif in_parentheses(fast_format, ["_s_", "slow", "methodical", "thorough"]):
        speed_multiplier = 0.75

    # Interruption / pause adjustment
    speech = speech.replace("…", "...").replace(". . .", "...").replace("—", "-")
    space_removal = speech.replace(" ", "")
    trailing_dots = len(space_removal) - len(space_removal.rstrip("."))
    trailing_dashes = len(space_removal) - len(space_removal.rstrip("-"))

    # More dots = longer pauses, more dashes = more abrupt interruptions
    if trailing_dashes >= 1:
        end_offset = map_range(min(4,trailing_dashes), 1, 2, 
                    -0.35 / speed_multiplier, 
                    -1.0 / speed_multiplier)
    elif trailing_dots >= 2:
        end_offset = map_range(min(6,trailing_dots), 2, 6, 
                    1 / speed_multiplier, 
                    5 / speed_multiplier)

    speech = remove_parenthesis(speech)

    script_lines.append(
        ScriptLine(speech, character, speed_multiplier, end_offset, start, end)
    )


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

        if line.upper() in character_voices:  # CHARACTER
            character = line.upper()
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


def in_parentheses(text, words):
    """Return True if any parenthesized text contains any word in words."""
    for match in re.findall(r"\((.*?)\)", text):
        if any(word in match for word in words):
            return True
    return False


def remove_parenthesis(text):
    return re.sub(r"\([^)]*\)", "", text)
