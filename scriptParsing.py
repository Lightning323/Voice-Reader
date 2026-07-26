import re


class ScriptLine:
    def __init__(self, text, character, speed_multiplier, end_offset, start, end):
        self.text = text
        self.character = character

        #Should we subtract N seconds or add N seconds to the audio file?
        self.end_offset = end_offset
        self.speed_multiplier=speed_multiplier

        #Line start and end
        self.start = start
        self.end = end

    def __str__(self):
        return f'{self.character}: "{self.text}" (offset={self.end_offset}; x{self.speed_multiplier}) ({self.start}-{self.end})'


def add_script_line(script_lines, speech, character, start, end):
    end_offset = 0
    speed_multiplier = 1

    if speech.endswith("--"):
        end_offset = -1.5
    elif speech.endswith(". . ."):
        end_offset = 2

    if speech.__contains__("fast") or speech.__contains__("frantic"):
        speed_multiplier = 1.5
    elif speech.__contains__("slow") or speech.__contains__("methodical"):
        speed_multiplier = 0.5

    speech = speech.replace(". . .", "")
    speech = remove_parenthesis(speech)

    script_lines.append(ScriptLine(speech, character, speed_multiplier, end_offset, start, end))


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
                add_script_line(script_lines, dialogue, character, i+1, i+1)
                i += 1

        else:  # If we dont have a character, it must be NARRATION
            while (
                i < len(lines)
                and lines[i].strip()
                and lines[i].upper() not in character_voices
            ):
                dialogue = lines[i].strip()
                add_script_line(
                    script_lines, dialogue, "NARRATOR", i+1, i+1
                )
                i += 1

    return script_lines


def remove_parenthesis(text):
    return re.sub(r"\([^)]*\)", "", text)
