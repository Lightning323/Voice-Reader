import re


def map_range(value, in_min, in_max, out_min, out_max):
    return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min


class ScriptLine:
    def __init__(
        self,
        text,
        character,
        speed_multiplier,
        end_offset,
        line_start,
        line_end,
        character_start=None,
        character_end=None,
    ):
        self.text = text.strip()
        self.character = character

        # Should we subtract N seconds or add N seconds to the audio file?
        self.end_offset = end_offset
        # How fast should we speak this line
        self.speed_multiplier = speed_multiplier

        # Line start and end
        self.start = line_start
        self.end = line_end

        # Character start and end
        self.character_start = character_start
        self.character_end = character_end

    def __repr__(self):
        return f"ScriptLine({self.text}, {self.character}, {self.speed_multiplier}, {self.end_offset}, {self.start}.{self.character_start}, {self.end}.{self.character_end})"


# ---------------------
# DIOLOGUE PARSING
# ---------------------

default_speed_multiplier = 1.0


def add_script_line(script_lines, speech, character, start, end):
    global default_speed_multiplier

    speech = speech.strip()
    speed_multiplier, speech, was_notated = calculate_speed_multiplier(speech)
    end_offset = calculate_end_offset(speech)

    if (
        was_notated and character == "NARRATOR" and format_line(speech).strip() == ""
    ):  # If the only thing on this line is a speed multiplier, set it as the default
        default_speed_multiplier = speed_multiplier
        print("Default speed multiplier set to", default_speed_multiplier)
        return

    speech = format_line(speech)

    # The narrator can't have a default speed multiplier
    if not was_notated and character == "NARRATOR":
        speed_multiplier = 1

    script_lines.append(
        ScriptLine(
            speech,
            character,
            speed_multiplier,
            end_offset,
            start,
            end,
        )
    )


SPEED_PATTERNS = [
    (
        1.6,
        ["fff-", "fff_", "(fff)"],
        [
            "_fff_",
            "-fff-",
            "very very fast",
            "very very rapid",
            "very very frantic",
            "very very quick",
        ],
    ),
    (
        1.45,
        ["ff-", "ff_", "(ff)"],
        ["_ff_", "-ff-", "very fast", "very rapid", "very frantic", "very quick"],
    ),
    (1.32, ["f-", "f_", "(f)"], ["_f_", "-f-", "fast", "rapid", "frantic", "quick"]),
    (
        0.5,
        ["sss-", "sss_", "(sss)"],
        [
            "_sss_",
            "-sss-",
            "very very slow",
            "very very methodical",
            "very very thorough",
        ],
    ),
    (
        0.6,
        ["ss-", "ss_", "(ss)"],
        ["_ss_", "-ss-", "very slow", "very methodical", "very thorough"],
    ),
    (0.75, ["s-", "s_", "(s)"], ["_s_", "-s-", "slow", "methodical", "thorough"]),
    (1.0, ["f-", "f_", "(f)"], ["reset", "normal", "-r-", "_r_"]),
]


def calculate_speed_multiplier(speech):
    global default_speed_multiplier
    for multiplier, starts_with, words_in_parentheses in SPEED_PATTERNS:
        for prefix in starts_with:
            if speech.lower().strip().startswith(prefix):
                return multiplier, speech[len(prefix) :].lstrip(), True

        if in_parentheses(speech, words_in_parentheses):
            return multiplier, speech, True

    return default_speed_multiplier, speech, False


def in_parentheses(text, words):
    formatted_text = " ".join(text.replace(",", "").replace(".", "").split()).lower()
    notes = " ".join(re.findall(r"\((.*?)\)", formatted_text))
    return any(word in notes for word in words)


def calculate_end_offset(speech):
    # Interruption / pause adjustment
    speech = speech.replace("…", "...").replace(". . .", "...").replace("—", "-")
    space_removal = speech.replace(" ", "")
    trailing_dots = len(space_removal) - len(space_removal.rstrip("."))
    trailing_dashes = len(space_removal) - len(space_removal.rstrip("-"))

    # More dots = longer pauses, more dashes = more abrupt interruptions
    # Interruptions
    if trailing_dashes >= 1:
        end_offset = map_range(
            min(3, trailing_dashes),
            1,
            2,
            -0.35,
            -1.0,
        )
    # Pauses
    elif trailing_dots >= 2:
        end_offset = map_range(min(6, trailing_dots), 2, 6, 1, 5)
    else:
        end_offset = 0

    return end_offset


def parse_script(text, character_voices):
    global default_speed_multiplier

    default_speed_multiplier = 1.0
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

    return script_lines, text


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
"""

raw text

    ↓
merge wrapped lines into paragraphs

If a line ends with sentence punctuation (., ?, !, : maybe), assume it might be complete.
If the next line starts lowercase, it is almost certainly a continuation.
If the current line does not end punctuation, merge it with the next line.
Preserve numbered lists.


    ↓
split paragraphs into sentences

    ↓
create ScriptLine objects



"""

import nltk

nltk.download("punkt")
nltk.download("punkt_tab")
from nltk.tokenize import sent_tokenize


def merge_lines_into_paragraphs(text):
    lines = text.splitlines()

    paragraphs = []
    buffer = ""
    start_line = None
    current_line = 0

    for line in lines:
        current_line += 1
        stripped = line.strip()

        if not stripped:
            if buffer:
                paragraphs.append((buffer, start_line, current_line - 1))
                buffer = ""
                start_line = None
            continue

        if start_line is None:
            start_line = current_line

        # Keep numbered list items separate
        if re.match(r"^\d+\s", stripped):
            if buffer:
                paragraphs.append((buffer, start_line, current_line - 1))
                buffer = ""
                start_line = current_line

            paragraphs.append((stripped, current_line, current_line))
            continue

        if buffer:
            buffer += " " + stripped
        else:
            buffer = stripped

    if buffer:
        paragraphs.append((buffer, start_line, current_line))

    return paragraphs


def parse_text(text):
    paragraphs = merge_lines_into_paragraphs(text)

    script_lines = []
    new_text = []

    for paragraph, paragraph_line_start, paragraph_line_end in paragraphs:

        sentences = sent_tokenize(paragraph)

        for sentence in sentences:
            new_text.append(sentence)

            speed_multiplier = 1.0
            end_offset = calculate_end_offset(sentence)

            sentence = format_line(sentence)

            line_start = len(new_text)

            script_line = ScriptLine(
                sentence,
                "NARRATOR",
                speed_multiplier,
                end_offset,
                line_start,
                line_start,
                0,
                0,
            )
            script_lines.append(script_line)
        new_text.append("")
    # TODO: It might be better to keep track of each sentence and read it without having to re-format the document
    return script_lines, "\n".join(new_text).rstrip()
