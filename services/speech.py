import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass
class Speech:
    speaker: Optional[str]
    transcript: str


class SpeechType(Enum):
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


def _classify_speech_type(parsed: list[Speech], speaker_count: int) -> SpeechType:
    if parsed:
        return SpeechType.PARSED
    if speaker_count == 1:
        return SpeechType.SINGLE_SPEAKER
    if speaker_count > 1:
        return SpeechType.MULTI_SPEAKER
    return SpeechType.NO_SPEAKER


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
    # (sc startswith ref), addenda/prefix mismatches (ref endswith sc), and lines with
    # a context prefix before the title (sc endswith ref, e.g. "[Chair] HEAD X").
    sc_norm = re.sub(r"\s+", "", stripped)
    ref_norm = re.sub(r"\s+", "", _strip_md(candidate).lower())
    if sc_norm and ref_norm and (
        sc_norm == ref_norm
        or (sc_norm.startswith(ref_norm) and len(ref_norm) > 8)
        or (ref_norm.endswith(sc_norm) and len(sc_norm) >= 10)
        or (sc_norm.endswith(ref_norm) and len(ref_norm) >= 10)
    ):
        return True

    # Strategy 5: strip chair-annotation prefix [X in the Chair] and trailing
    # parenthetical suffix before comparing — handles lines like
    # "**[Mr Speaker in the Chair] TITLE (Announcement by Mr Speaker)**"
    no_chair = re.sub(r"^\[.*?\]\s*", "", stripped).strip()
    no_suffix = re.sub(r"\s*\([^)]*\)\s*$", "", no_chair).strip()
    sc_norm5 = re.sub(r"\s+", "", no_suffix.lower())
    if sc_norm5 and sc_norm5 == ref_norm:
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


def _parse_speeches(markdown: str, start_of_speech_line: int) -> list[Speech]:
    current_speaker = None
    speeches: list[Speech] = []
    for line in markdown.splitlines()[start_of_speech_line + 1 :]:
        parsed_line = line.strip()
        if not parsed_line:
            continue
        if not parsed_line.strip("* "):  # skip artifact lines: **, ****, ** **, etc.
            continue
        if "**" not in parsed_line:
            if current_speaker is None:  # skip preamble before first speaker
                continue
            speeches.append(Speech(speaker=current_speaker, transcript=parsed_line))
            continue

        name = re.search(r"((?:\*\*[^*]+?\*\*\s*)+)", parsed_line)
        if name:
            transcript = parsed_line.split(name.group(0))[-1].strip()
            new_speaker = name.group(0).replace("*", "").replace(":", "").strip()
            if new_speaker:  # guard: don't overwrite speaker with empty string
                current_speaker = new_speaker
            if current_speaker is not None:
                speeches.append(Speech(speaker=current_speaker, transcript=transcript))
            continue

        if current_speaker is not None:
            speeches.append(Speech(speaker=current_speaker, transcript=parsed_line))

    return [sp for sp in speeches if sp.transcript.strip() != ""]


def get_speeches(markdown: str, start_of_speech_line: int) -> list[Speech]:
    parsed = _parse_speeches(markdown, start_of_speech_line)
    speakers = _extract_mps_speaking(markdown)
    speech_type = _classify_speech_type(parsed, len(speakers))

    if speech_type == SpeechType.PARSED:
        return parsed
    if speech_type == SpeechType.SINGLE_SPEAKER:
        body = _single_speaker_transcript(markdown, start_of_speech_line)
        return [Speech(speaker=speakers[0], transcript=body)] if body else []
    return []
