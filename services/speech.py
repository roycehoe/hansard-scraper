import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from utils.text import fix_mojibake


@dataclass
class ParsedSpeech:
    speaker: Optional[str]
    transcript: str


class ParsedSpeechType(Enum):
    PARSED = "parsed"
    SINGLE_SPEAKER = "single_speaker"
    MULTI_SPEAKER = "multi_speaker"
    NO_SPEAKER = "no_speaker"


_MP_SPEAK_RE = re.compile(r"MPs? Speaking:\|[ \t]*([^\n|]+)", re.IGNORECASE)

# atbp — Speaker signature at the end of Assents to Bills Passed notices:
# | FULL NAME
# ---|---
# | _Speaker_
_ATBP_SPEAKER_RE = re.compile(
    r"\|\s+([A-Z][A-Z '.-]+?)\s*\n-+\|-+\s*\n\|[^\n]*[Ss]peaker",
    re.MULTILINE,
)

# president-address addenda (old format, Parliament 11 and earlier):
# **MINISTRY OF ...** or **PRIME MINISTER'S OFFICE...**
# MR / DR / ... NAME
# Minister for ... / Deputy / etc.
_ADDENDA_MINISTER_RE = re.compile(
    r"\*\*[^\n*]*(?:MINISTRY|PRIME MINISTER)[^\n*]*\*\*\n"
    r"((?:Mr|Mrs|Ms|Dr|Prof|Mdm|MR|DR|MDM|PROF|Assoc)\s+[A-Z][A-Za-z '.()\-]+)\n"
    r"(?:Minister|Deputy|Senior|Acting|Second|Secretary|Permanent|Political|Director)",
    re.MULTILINE | re.IGNORECASE,
)

# Used to detect whether a president-address doc contains a ministry heading at all
# (addendum) vs. not (actual presidential speech).
_MINISTRY_HEADING_RE = re.compile(
    r"\*\*[^\n*]*(?:MINISTRY|PRIME MINISTER)[^\n*]*\*\*",
    re.IGNORECASE,
)

# motion adjournment mover: "- [Dr Ng Eng Hen]" or "− [Mr Mah Bow Tan]"
_ADJOURNMENT_MOVER_RE = re.compile(
    r"[−\-]\s*\[((?:Mr|Mrs|Ms|Dr|Prof|Mdm|Assoc\s+Prof)[^]]+)\]",
    re.IGNORECASE,
)

# bill First Reading presenter: "presented by ... (Mrs Lim Hwee Hua)"
_BILL_PRESENTER_RE = re.compile(
    r"presented\s+by[^(]*\(([^)]+)\)",
    re.IGNORECASE,
)

# Honorific prefixes used in speaker names — absent means the bold line is a title/heading, not a speaker
_SPEAKER_HONORIFIC_RE = re.compile(
    r"\b(Mr|Mrs|Ms|Dr|Prof|Mdm|Assoc|Inche|Tuan|Haji|The|Er)\b"
)


def _extract_mps_speaking(markdown: str) -> list[str]:
    match = _MP_SPEAK_RE.search(markdown)
    if not match:
        return []
    return [part.strip() for part in match.group(1).split(";") if part.strip().strip("* ")]


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
        stripped
        for line in markdown.splitlines()[start_of_speech_line + 1:]
        if (stripped := line.strip()) and stripped.strip("* ")
    )


def _is_section_header_speaker(name: str) -> bool:
    """True if the name looks like a topic/section header, not a person."""
    stripped = name.strip()
    if not stripped:
        return False
    if re.search(r"\b(Mr|Mrs|Ms|Dr|Prof|Mdm|Assoc)\b", stripped):
        return False
    if re.search(r"\b(President|Speaker|Minister|Secretary|Deputy|Senior|Acting)\b", stripped, re.IGNORECASE):
        return False
    return stripped == stripped.upper()


def _extract_addenda_minister(markdown: str) -> Optional[str]:
    match = _ADDENDA_MINISTER_RE.search(markdown)
    return match.group(1).strip() if match else None


def _extract_body_attribution(markdown: str, report_type: str) -> Optional[str]:
    """
    For docs where MPs Speaking is absent or empty, return the single author
    inferred from body content. Returns None if no attribution can be determined.

    Patterns handled:
      atbp            — Speaker signature block at the foot of the notice
      president-address — minister name after bold ministry heading (addenda), or
                          "The President" for the actual presidential speech
      motion          — mover named in square brackets in the adjournment clause
      bill            — presenter named in the "presented by (Name)" clause
    """
    if report_type == "atbp":
        match = _ATBP_SPEAKER_RE.search(markdown)
        return match.group(1).strip() if match else None

    if report_type == "president-address":
        minister = _extract_addenda_minister(markdown)
        if minister:
            return minister
        # No ministry heading → actual presidential speech, not an addendum
        if not _MINISTRY_HEADING_RE.search(markdown):
            return "The President"
        return None

    if report_type == "motion":
        match = _ADJOURNMENT_MOVER_RE.search(markdown)
        return match.group(1).strip() if match else None

    if report_type == "bill":
        match = _BILL_PRESENTER_RE.search(markdown)
        return match.group(1).strip() if match else None

    return None


def _strip_md(text: str) -> str:
    return re.sub(r"[_*]", "", text)


def _extract_md_title(markdown_content: str) -> Optional[str]:
    """Extract the Title field from the markdown header row, if present."""
    for line in markdown_content.splitlines()[:12]:
        match = re.search(r"Title:\|\s*([^|\n]+)", line, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
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
    title = fix_mojibake(title)
    subtitle = fix_mojibake(subtitle) if subtitle else subtitle
    original_title = fix_mojibake(original_title)
    original_title_clean = original_title.replace("\n", " ").strip()

    # Extract the title as written in the markdown header — may differ from the DB
    # title due to HTML entity artifacts, OCR noise, or data entry errors.
    md_title = fix_mojibake(_extract_md_title(markdown_content) or "")

    candidates = [candidate for candidate in [
        title,
        original_title_clean,
        f"{title} {subtitle}" if subtitle else None,
        md_title or None,
    ] if candidate]

    for line_index, line in enumerate(markdown_content.splitlines()):
        for candidate in candidates:
            if _line_matches_title(line, candidate):
                return line_index

    return None


def _is_artifact_line(line: str) -> bool:
    if not line:
        return True
    if not line.strip("* _|"):
        return True
    if re.match(r"^-{3}(\|-{2,})+\s*$", line):
        return True
    if line.startswith("!["):
        return True
    if line == "﻿":
        return True
    return False


def _parse_speeches(markdown: str, start_of_speech_line: int) -> list[ParsedSpeech]:
    current_speaker = None
    speeches: list[ParsedSpeech] = []
    for line in markdown.splitlines()[start_of_speech_line + 1 :]:
        parsed_line = line.strip()
        parsed_line = re.sub(r"^(\*{4})+", "", parsed_line)  # strip leading **** artifacts (e.g. ****8.**Name**)
        if _is_artifact_line(parsed_line):
            continue
        if "**" not in parsed_line:
            if current_speaker is None:  # skip preamble before first speaker
                continue
            if re.match(r"^\d{1,2}\.\d{2}\s*[ap]\.?m\.?$", parsed_line, re.IGNORECASE):
                continue  # skip procedural time markers (e.g. "4.26 pm", "3.30 p.m.")
            if re.match(r"^#{1,6}(\s|$)", parsed_line):
                continue  # skip markdown section headings (e.g. "#### [Mr SPEAKER in the Chair]")
            speeches.append(ParsedSpeech(speaker=current_speaker, transcript=parsed_line))
            continue

        bold_match = re.search(r"((?:\*\*[^*]+?\*\*\s*)+)", parsed_line)
        if bold_match:
            transcript = re.sub(r"^:\s*", "", parsed_line.split(bold_match.group(0))[-1].strip())
            if transcript.startswith("|"):
                continue  # table row header ("**Header** | ...") — bold is a column label, not a speaker
            raw_speaker = bold_match.group(0).replace("*", "").replace(":", "").strip()
            # Strip [X in the Chair] chair-annotation prefix (e.g. "**[Mr Speaker in the Chair] BILL**")
            chair_match = re.match(r"^\[(.+?)\s+in the [Cc]hair\]", raw_speaker)
            new_speaker = chair_match.group(1).strip() if chair_match else raw_speaker
            # Skip bold section-title lines: no honorific AND (no colon, or colon is mid-title
            # not at the end). Catches "**MINISTRY OF EDUCATION**", "**Table 1: Description**".
            bold_ends_with_colon = bold_match.group(0).rstrip().endswith(":**")
            if (not transcript
                    and not _SPEAKER_HONORIFIC_RE.search(raw_speaker)
                    and (":" not in bold_match.group(0) or not bold_ends_with_colon)):
                continue
            # Strip leading question-number prefix from oral-answer speaker names
            # e.g. "1\. Assoc. Prof. Paulin Tay Straughan" → "Assoc. Prof. Paulin Tay Straughan"
            new_speaker = re.sub(r"^\d+\\?\.\s+", "", new_speaker)
            if new_speaker:  # guard: don't overwrite speaker with empty string
                current_speaker = new_speaker
            if current_speaker is not None:
                speeches.append(ParsedSpeech(speaker=current_speaker, transcript=transcript))
            continue

        if current_speaker is not None:
            speeches.append(ParsedSpeech(speaker=current_speaker, transcript=parsed_line))

    return [speech for speech in speeches if speech.transcript.strip() != ""]


def get_speeches(markdown: str, start_of_speech_line: int, report_type: str) -> list[ParsedSpeech]:
    parsed = _parse_speeches(markdown, start_of_speech_line)
    speakers = _extract_mps_speaking(markdown)
    speech_type = _classify_speech_type(parsed, len(speakers))

    if speech_type == ParsedSpeechType.PARSED:
        # Old-format docs use bold section headers (e.g. **ASSENTS TO BILLS PASSED**,
        # **EXTERNAL ENVIRONMENT**) that _parse_speeches misidentifies as speakers.
        # When MPs Speaking is empty and the first parsed speaker looks like a
        # section header, collapse everything to a single correctly-attributed speech.
        if (report_type in ("president-address", "atbp")
                and not speakers
                and parsed
                and _is_section_header_speaker(parsed[0].speaker)):
            speaker = _extract_body_attribution(markdown, report_type)
            if speaker:
                body = _single_speaker_transcript(markdown, start_of_speech_line)
                return [ParsedSpeech(speaker=speaker, transcript=body)] if body else []
        return parsed

    if speech_type == ParsedSpeechType.SINGLE_SPEAKER:
        body = _single_speaker_transcript(markdown, start_of_speech_line)
        return [ParsedSpeech(speaker=speakers[0], transcript=body)] if body else []

    if speech_type == ParsedSpeechType.NO_SPEAKER:
        speaker = _extract_body_attribution(markdown, report_type)
        if speaker:
            body = _single_speaker_transcript(markdown, start_of_speech_line)
            return [ParsedSpeech(speaker=speaker, transcript=body)] if body else []

    return []
