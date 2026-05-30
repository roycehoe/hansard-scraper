import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass
class ParsedSpeech:
    speaker: Optional[str]
    transcript: str


class ParsedSpeechType(Enum):
    PARSED = "parsed"
    SINGLE_SPEAKER = "single_speaker"
    MULTI_SPEAKER = "multi_speaker"
    NO_SPEAKER = "no_speaker"


_MP_SPEAK_RE = re.compile(r"MPs? Speaking:\|\s*([^\n|]+)", re.IGNORECASE)


def _extract_mps_speaking(markdown: str) -> list[str]:
    m = _MP_SPEAK_RE.search(markdown)
    if not m:
        return []
    return [n.strip() for n in m.group(1).split(";") if n.strip().strip("* ")]


def _classify_speech_type(parsed: list[ParsedSpeech], speaker_count: int) -> ParsedSpeechType:
    if parsed:
        return ParsedSpeechType.PARSED
    if speaker_count == 1:
        return ParsedSpeechType.SINGLE_SPEAKER
    if speaker_count > 1:
        return ParsedSpeechType.MULTI_SPEAKER
    return ParsedSpeechType.NO_SPEAKER


def _single_speaker_transcript(markdown: str, start_of_speech_line: int) -> str:
    return " ".join(
        line.strip()
        for line in markdown.splitlines()[start_of_speech_line + 1:]
        if line.strip() and line.strip().strip("* ")
    )


def _strip_md(text: str) -> str:
    return re.sub(r"[_*]", "", text)


# TODO: remove once the pipeline has been rerun — mojibake is now fixed upstream in
# services/report.py at Report creation time, so titles stored in the DB will already
# be clean and these call sites will be dead.
def _fix_mojibake(s: str) -> str:
    """Fix Windows-1252 mojibake in stored titles (e.g. â€™ → ', âˆ' → −)."""
    try:
        return s.encode("cp1252").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


def _extract_md_title(markdown_content: str) -> Optional[str]:
    """Extract the Title field from the markdown header row, if present."""
    for line in markdown_content.splitlines()[:12]:
        m = re.search(r"Title:\|\s*([^|\n]+)", line, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if candidate:
                return candidate
    return None


def _line_matches_title(line: str, candidate: str) -> bool:
    """Return True if the line matches the candidate title via any strategy."""
    # Strategy 1: closed bold (**title**) — old format with proper closing
    if f"{candidate}**" in line:
        return True

    # Strategy 2: markdown heading (# title) — new format (Parliament 12+)
    if line.startswith("#"):
        heading = _strip_md(line.lstrip("#").strip()).lower()
        if heading == _strip_md(candidate).lower():
            return True

    # Strategy 3: stripped content — italic, open bold, plain text (old format)
    stripped = _strip_md(line).strip().lower()
    if stripped and stripped == _strip_md(candidate).lower():
        return True

    # Strategy 4: whitespace-normalized — OCR-damaged spacing, continuation markers
    # (line startswith candidate), addenda/prefix mismatches (candidate endswith line), and lines with
    # a context prefix before the title (line endswith candidate, e.g. "[Chair] HEAD X").
    line_norm = re.sub(r"\s+", "", stripped)
    candidate_norm = re.sub(r"\s+", "", _strip_md(candidate).lower())
    if line_norm and candidate_norm and (
        line_norm == candidate_norm
        or (line_norm.startswith(candidate_norm) and len(candidate_norm) > 8)
        or (candidate_norm.endswith(line_norm) and len(line_norm) >= 10)
        or (line_norm.endswith(candidate_norm) and len(candidate_norm) >= 10)
    ):
        return True

    # Strategy 5: strip chair-annotation prefix [X in the Chair] and trailing
    # parenthetical suffix before comparing — handles lines like
    # "**[Mr Speaker in the Chair] TITLE (Announcement by Mr Speaker)**"
    no_chair = re.sub(r"^\[.*?\]\s*", "", stripped).strip()
    no_suffix = re.sub(r"\s*\([^)]*\)\s*$", "", no_chair).strip()
    line_norm_no_chair = re.sub(r"\s+", "", no_suffix.lower())
    if line_norm_no_chair and line_norm_no_chair == candidate_norm:
        return True

    return False


def get_start_of_speech_line(
    markdown_content: str,
    title: str,
    subtitle: Optional[str],
    original_title: str,
    report_type: str = "",
) -> Optional[int]:
    title = _fix_mojibake(title)
    subtitle = _fix_mojibake(subtitle) if subtitle else subtitle
    original_title = _fix_mojibake(original_title)
    original_title_clean = original_title.replace("\n", " ").strip()

    # Extract the title as written in the markdown header — may differ from the DB
    # title due to HTML entity artifacts, OCR noise, or data entry errors.
    md_title = _fix_mojibake(_extract_md_title(markdown_content) or "")

    candidates = [c for c in [
        title,
        original_title_clean,
        f"{title} {subtitle}" if subtitle else None,
        md_title or None,
    ] if c]

    for line_index, line in enumerate(markdown_content.splitlines()):
        for candidate in candidates:
            if _line_matches_title(line, candidate):
                return line_index

    return None


def _parse_speeches(markdown: str, start_of_speech_line: int) -> list[ParsedSpeech]:
    current_speaker = None
    speeches: list[ParsedSpeech] = []
    for line in markdown.splitlines()[start_of_speech_line + 1 :]:
        parsed_line = line.strip()
        if not parsed_line:
            continue
        if not parsed_line.strip("* "):  # skip artifact lines: **, ****, ** **, etc.
            continue
        if "**" not in parsed_line:
            if current_speaker is None:  # skip preamble before first speaker
                continue
            speeches.append(ParsedSpeech(speaker=current_speaker, transcript=parsed_line))
            continue

        name = re.search(r"((?:\*\*[^*]+?\*\*\s*)+)", parsed_line)
        if name:
            transcript = parsed_line.split(name.group(0))[-1].strip()
            new_speaker = name.group(0).replace("*", "").replace(":", "").strip()
            if new_speaker:  # guard: don't overwrite speaker with empty string
                current_speaker = new_speaker
            if current_speaker is not None:
                speeches.append(ParsedSpeech(speaker=current_speaker, transcript=transcript))
            continue

        if current_speaker is not None:
            speeches.append(ParsedSpeech(speaker=current_speaker, transcript=parsed_line))

    return [sp for sp in speeches if sp.transcript.strip() != ""]


def get_speeches(markdown: str, start_of_speech_line: int) -> list[ParsedSpeech]:
    parsed = _parse_speeches(markdown, start_of_speech_line)
    speakers = _extract_mps_speaking(markdown)
    speech_type = _classify_speech_type(parsed, len(speakers))

    if speech_type == ParsedSpeechType.PARSED:
        return parsed
    if speech_type == ParsedSpeechType.SINGLE_SPEAKER:
        body = _single_speaker_transcript(markdown, start_of_speech_line)
        return [ParsedSpeech(speaker=speakers[0], transcript=body)] if body else []
    return []
