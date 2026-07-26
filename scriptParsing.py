import re

class ScriptLine:
    def __init__(self, text, character, end_offset, start, end):
        self.text = text
        self.character = character
        self.end_offset = end_offset
        self.start = start
        self.end = end

    def __str__(self):
        return f"{self.character}: \"{self.text}\" (offset={self.end_offset}) ({self.start}-{self.end})"

def add_script_lines(script_lines, dialogue, character, start, end):
    speech = " ".join(dialogue).strip()

    print(speech)

    end_offset = 0
    if(speech.endswith("--")):
        end_offset = -2
    elif(speech.endswith(". . .")):
        end_offset = 2

    speech = speech.replace(". . .", "")
    speech = remove_parenthesis(speech)

    script_lines.append(
        ScriptLine(speech, character, end_offset, start, end)
    )

def parse_script(text, character_voices):
    script_lines = []
    #Get the lines

    lines = text.splitlines()
    
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        # -------------------------
        # CHARACTER
        # -------------------------

        if line.upper() in character_voices:
            character = line.upper()
            start = i + 2
            dialogue = []
            i += 1

            while i < len(lines) and lines[i].strip():
                dialogue.append(lines[i].strip())
                i += 1
            end = i + 1
            add_script_lines(script_lines, dialogue, character, start, end)

        # -------------------------
        # If we dont have a character, it must be NARRATION
        # -------------------------

        else:
            start = i + 1
            narration = []
            while (
                i < len(lines)
                and lines[i].strip()
                and lines[i].upper() not in character_voices
            ):
                narration.append(lines[i].strip())
                i += 1
            end = i + 1
            add_script_lines(script_lines, narration, "NARRATOR", start, end)


    return script_lines


def remove_parenthesis(text):
    return re.sub(r"\([^)]*\)", "", text)