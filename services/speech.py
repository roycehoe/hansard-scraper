import json
from dataclasses import dataclass
from typing import Optional

from database.report import Report


@dataclass
class Speech:
    speaker: Optional[str]
    transcript: str


def get_start_of_speech_line(
    markdown_content: str, title: str, subtitle: Optional[str]
) -> Optional[int]:
    possible_start_of_speech_lines = []

    for line_index, line in enumerate(markdown_content.splitlines()):
        if subtitle and f"# {subtitle}" in line:
            possible_start_of_speech_lines.append(line_index)
        if f"# {title}" in line:
            possible_start_of_speech_lines.append(line_index)

    for line_index, line in enumerate(markdown_content.splitlines()):
        if subtitle and f"*{subtitle}" in line:
            possible_start_of_speech_lines.append(line_index)
        if f"*{title}" in line:
            possible_start_of_speech_lines.append(line_index)

    if len(possible_start_of_speech_lines) == 0:
        return None

    return max(possible_start_of_speech_lines)


def contains_speaker_name(line: str):
    return "**" in line


def get_speeches(markdown: str, start_of_speech_line: int):
    current_speaker = None
    speeches = []
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
        _, name, transcript = parsed_line.split("**")
        current_speaker = name[:-1] if name.endswith(":") else name
        transcript = transcript[3:] if transcript.startswith(" : ") else transcript

        speeches.append(
            Speech(
                speaker=current_speaker,
                transcript=transcript.strip(),
            )
        )
    return speeches


with open("sample.json") as json_data:
    data = json.load(json_data)

reports = [Report(**i) for i in data]
for report in reports:
    if report.markdown_content:
        start_of_speech_line = get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle
        )
        if start_of_speech_line is None:
            raise Exception("No start of speech line found!")
        speeches = get_speeches(report.markdown_content, start_of_speech_line)
