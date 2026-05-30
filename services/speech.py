import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Speech:
    speaker: Optional[str]
    transcript: str


def _strip_md(text: str) -> str:
    return re.sub(r"[_*]", "", text)


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
