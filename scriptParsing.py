import re

class ScriptLine:
    def __init__(self, text, sentence, character, start, end):
        self.text = text
        self.character = character
        self.start = start
        self.end = end
        self.sentence = sentence

    def __str__(self):
        return f"{self.character}: \"{self.sentence}\" ({self.start}-{self.end})"

def parse_script(text, character_voices):
    script_lines = []
    #Get the lines

    lines = text.splitlines()
    
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        line = preformat_text(line)

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
            speech = ". ".join(dialogue)
            for sentence in split_sentences(speech):
                script_lines.append( ScriptLine(speech, sentence, character, start, end))

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
            speech = ". ".join(narration)
            for sentence in split_sentences(speech):
                script_lines.append( ScriptLine(speech, sentence, "NARRATOR", start, end))

    # for line in script_lines:
    #     print(line,"\n")
    return script_lines


def preformat_text(text):
    return re.sub(r"\([^)]*\)", "", text)

def split_sentences(text):
    return re.split(r"(?<=[.!?])\s+", text)