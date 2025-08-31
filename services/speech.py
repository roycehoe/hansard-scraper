import json
from dataclasses import dataclass
import re
from typing import Optional

from sqlmodel import select

from database.init import get_session
from database.report import Report


@dataclass
class Speech:
    speaker: Optional[str]
    transcript: str


def get_start_of_speech_line(
    markdown_content: str, title: str, subtitle: Optional[str], original_title: str
) -> Optional[int]:
    for line_index, line in enumerate(markdown_content.splitlines()):
        if subtitle:
            if f"{title} {subtitle}**" in line:
                return line_index
            if line.endswith(f"{subtitle}**"):
                return line_index
            if f"{subtitle}**" in line:
                return line_index
        if f"{title}**" in line:
            return line_index
        if f"{original_title.lower()}**" in line.lower():
            return line_index
        if f"{original_title.lower().replace(' ','')}**" in line.lower().replace(
            " ", ""
        ):
            return line_index
    return None


def contains_speaker_name(line: str):
    return "**" in line


def get_speeches(markdown: str, start_of_speech_line: int) -> list[Speech]:
    current_speaker = None
    speeches: list[Speech] = []
    for line in markdown.splitlines()[start_of_speech_line + 1 :]:
        parsed_line = line.strip()
        if parsed_line == "":
            continue
        if parsed_line == "**":
            continue
        if not contains_speaker_name(parsed_line):
            speeches.append(Speech(speaker=current_speaker, transcript=line.strip()))
            continue

        # TODO: 20890 causing problems
        name = re.search(r"((?:\*\*[^*]+?\*\*\s*)+)", parsed_line)
        if name:
            transcript = parsed_line.split(name.group(0))[-1]
            current_speaker = name.group(0).replace("*", "").replace(":", "").strip()
            speeches.append(
                Speech(
                    speaker=current_speaker,
                    transcript=transcript.strip(),
                )
            )
            continue

        speeches.append(
            Speech(
                speaker=current_speaker,
                transcript=line.strip(),
            )
        )
    return speeches
