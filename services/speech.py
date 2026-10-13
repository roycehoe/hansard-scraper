import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from enums import ReportType
from utils.text import fix_mojibake


@dataclass
class ParsedSpeech:
    speaker: Optional[str]
    transcript: str


class ParsedSpeechType(Enum):
    PARSED = "PARSED"
    SINGLE_SPEAKER = "SINGLE_SPEAKER"
    MULTI_SPEAKER = "MULTI_SPEAKER"
    NO_SPEAKER = "NO_SPEAKER"


_MP_SPEAK_RE = re.compile(r"MPs? Speaking:\|[ \t]*([^\n|]+)", re.IGNORECASE)

_ATBP_SPEAKER_RE = re.compile(
    r"\|\s+([A-Z][A-Z '.-]+?)\s*\n-+\|-+\s*\n\|[^\n]*[Ss]peaker",
    re.MULTILINE,
)

_ADDENDA_MINISTER_RE = re.compile(
    r"\*\*[^\n*]*(?:MINISTRY|PRIME MINISTER)[^\n*]*\*\*\n"
    r"((?:Mr|Mrs|Ms|Dr|Prof|Mdm|MR|DR|MDM|PROF|Assoc)\s+[A-Z][A-Za-z '.()\-]+)\n"
    r"(?:Minister|Deputy|Senior|Acting|Second|Secretary|Permanent|Political|Director)",
    re.MULTILINE | re.IGNORECASE,
)

_MINISTRY_HEADING_RE = re.compile(
    r"\*\*[^\n*]*(?:MINISTRY|PRIME MINISTER)[^\n*]*\*\*",
    re.IGNORECASE,
)

_LANGUAGE_NOTE_RE = re.compile(
    r"[_*]*\(\s*[_*]*\s*(?:in|dalam)\s+(?:Mandar\w+|Malay|English|Tamil|Hokkien|Cantonese|Teochew|Hakka)\s*[_*]*\s*\)[_*]*\s*:?\s*",
    re.IGNORECASE,
)

_ADJOURNMENT_MOVER_RE = re.compile(
    r"[−\-]\s*\[((?:Mr|Mrs|Ms|Dr|Prof|Mdm|Assoc\s+Prof)[^]]+)\]",
    re.IGNORECASE,
)

_BILL_PRESENTER_RE = re.compile(
    r"presented\s+by[^(]*\(([^)]+)\)",
    re.IGNORECASE,
)

_SPEAKER_HONORIFIC_RE = re.compile(
    r"\b(Mr|Mrs|Ms|Dr|Prof|Mdm|Assoc|Inche|Tuan|Haji|The|Er)\b"
)

_PROCEDURAL_STAGE_RE = re.compile(
    r"^(First|Second|Third)\s+Reading$|^Committee$|^,$|^Year$",
    re.IGNORECASE,
)

_PROCEDURAL_LINE_ANCHORS = (
    r"Question (?:put,? and agreed to|proposed|again proposed)",
    r"Question put,? and negatived",
    r"Amendment, by leave, withdrawn",
    r"The sum of \$?[0-9,]+ .*ordered to stand part",  # Committee of Supply head
    r"Clauses? [0-9A-Za-z, to and]{1,30} ordered to stand part",
    r"Bill (?:accordingly )?read a (?:Second|Third|second|third) time",
    r"Bill reported without amendment",
    r"Bill considered in Committee",
    r"Resolution to be reported",
    r"Resolved(?:,|[\s*_]*$)",
    r"Order for Second Reading read",
    r"Order read for",
    r"Adjourned accordingly",
    r"Thereupon (?:Mr|Mdm) (?:Deputy )?Speaker",
    r"(?:Sitting|Debate) (?:according(?:ly)? )?(?:suspended|resumed)",
    r"Suspension of Sitting",
    r"resumed at \d",  # second half of a split suspension line
    r"\d{1,2}\.\d{2} [ap]\.?m\.? until \d|_\d{1,2}\.\d{2} [ap]\.?m\.? to \d",
    r"[A-Z][a-z]+(?:-[a-z]+)? minutes? (?:past|to) [A-Z][a-z]+ o'clock",
    r"(?:Amendment|Notice of motion|Copies of [^.]{0,80}) handed in(?: to the Clerk| and distributed to hon\. Members)?\.?$",
    r"No Member rising",
    r"\*\s*The same amendment",
    r"The (?:House|Assembly|Council|Committee) divided",
    r"Division taken",
    r"The following amendments? stood on the Order Paper",
)
_PROCEDURAL_LINE_RE = re.compile(r"^[\s*_]*(?:" + "|".join(_PROCEDURAL_LINE_ANCHORS) + ")")

_LIST_OPENER_RE = re.compile(
    r"^[\s*_]*(?:Resolved,?[\s*_]*$|The (?:House|Assembly|Council|Committee) divided|Division taken"
    r"|The following amendments? stood on the Order Paper)"
)

_PLAIN_HONORIFIC = r"(?:Mr|Mrs|Ms|Miss|Mdm|Madam|Dr|Prof|Assoc\.? Prof|Inche|Encik|Tuan|Haji|Che|Er|BG|RAdm|LG|MG|COL)\.?"
_PLAIN_ROLE_WORD = r"(?:[A-Z][A-Za-z'’.,&-]*|of|for|the|and|to)"
# NOTE: A bare name label such as "Mr Tan:" is not matched: it is often a line quoted inside another speech.
_PLAIN_ROLE_LABEL_RE = re.compile(
    r"^(The (?=[^:()]*\b(?:Minister|Secretary|Chairman|President|Leader|Attorney|Speaker)\b)"
    + _PLAIN_ROLE_WORD + r"(?: " + _PLAIN_ROLE_WORD + r"){0,15} \(" + _PLAIN_HONORIFIC + r" [^()]{2,50}\)"
    r"(?:\s*\([^()]{1,100}\))*)\s*:\s*(.*)$"
)

# NOTE: The list is explicit on purpose: other headings sit inside a member's speech.
_SECTION_BOUNDARY_HEADINGS = frozenset({
    "ADJOURNMENT",
    "ADJOURNMENT OF DEBATE",
    "ADJOURNMENT TO A DATE TO BE FIXED",
    "ADJOURNMENT SINE DIE",
    "REARRANGEMENT OF ORDER OF BUSINESS",
    "COMMITTEE OF SUPPLY",
})

_WHOLE_BOLD_LINE_RE = re.compile(r"^\*\*[^*].*\*\*$")


_MARKDOWN_TITLE_SCAN_LINES = 12
_PREFIX_TITLE_LENGTH_FLOOR = 8
_MIN_AFFIX_TITLE_LENGTH = 10
_MAX_SPEAKER_NAME_LENGTH = 80
_OPENING_QUOTE_MARKS = "\"“'"

_SPEAKER_ROLE_WORD_RE = re.compile(r"\b(President|Speaker|Minister|Secretary|Deputy|Senior|Acting)\b", re.IGNORECASE)
_MARKDOWN_TITLE_RE = re.compile(r"Title:\|\s*([^|\n]+)", re.IGNORECASE)
_MARKDOWN_MARKS_RE = re.compile(r"[_*]")
_QUOTE_MARKS_RE = re.compile(r"[\"“”]")
_WHITESPACE_RE = re.compile(r"\s+")
_CHAIR_PREFIX_RE = re.compile(r"^\[.*?\]\s*")
_TRAILING_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)\s*$")
_TRAILING_ACRONYM_RE = re.compile(r"\s*\([A-Z]+\)$")
_TABLE_RULE_RE = re.compile(r"^-{3}(\|-{2,})+\s*$")
_BOLD_ONLY_LINE_RE = re.compile(r"^\*\*([^*]+)\*\*\s*$")
_BOLD_OPENING_RE = re.compile(r"^\*\*(?!\*)")
_LEADING_BOLD_ARTIFACT_RE = re.compile(r"^(\*{4})+")
_TIME_MARKER_RE = re.compile(r"^\d{1,2}\.\d{2}\s*[ap]\.?m\.?$", re.IGNORECASE)
_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}(\s|$)")
_BOLD_RUN_RE = re.compile(r"((?:\*\*[^*]+?\*\*\s*)+)")
_LEADING_COLON_RE = re.compile(r"^:\s*")
_CHAIR_ANNOTATION_FULL_RE = re.compile(r"[\[(]?\s*.+?\s*in the [Cc]hair\s*[.\])]*")
_CHAIR_ANNOTATION_PREFIX_RE = re.compile(r"[\[(]\s*.+?\s*in the [Cc]hair\s*[.\])]")
_ALPHANUMERIC_RE = re.compile(r"[A-Za-z0-9]")
_LETTER_RE = re.compile(r"[A-Za-z]")
_QUESTION_NUMBER_PREFIX_RE = re.compile(r"^\d+\\?\.\s+")
_UNSPACED_HONORIFIC_RE = re.compile(r"^(Mr|Mrs|Ms|Dr|Prof|Mdm|The|BG|RAdm|Er)([A-Z])")
_DROP_CAP_RE = re.compile(r"[A-Za-z]{1,2}")
_PARENTHESISED_RE = re.compile(r"^\(.*\)$")
_ITALIC_HEADING_RE = re.compile(r"^_[^_].*_$")


def _extract_mps_speaking(markdown: str) -> list[str]:
    match = _MP_SPEAK_RE.search(markdown)
    if match is None:
        return []
    return [part.strip() for part in match.group(1).split(";") if part.strip().strip("* ")]


def _classify_speech_type(parsed_speeches: list[ParsedSpeech], speaker_count: int) -> ParsedSpeechType:
    if parsed_speeches:
        return ParsedSpeechType.PARSED
    if speaker_count == 1:
        return ParsedSpeechType.SINGLE_SPEAKER
    if speaker_count > 1:
        return ParsedSpeechType.MULTI_SPEAKER
    return ParsedSpeechType.NO_SPEAKER


def _get_single_speaker_transcript(markdown: str, start_of_speech_line: int) -> str:
    return " ".join(
        stripped
        for line in markdown.splitlines()[start_of_speech_line + 1:]
        if (stripped := line.strip()) and stripped.strip("* ")
    )


def _is_section_header_speaker(name: str) -> bool:
    stripped = name.strip()
    if not stripped:
        return False
    if _SPEAKER_HONORIFIC_RE.search(stripped):
        return False
    if _SPEAKER_ROLE_WORD_RE.search(stripped):
        return False
    return stripped == stripped.upper()


def _extract_addenda_minister(markdown: str) -> Optional[str]:
    match = _ADDENDA_MINISTER_RE.search(markdown)
    return match.group(1).strip() if match is not None else None


def _extract_body_attribution(markdown: str, report_type: str) -> Optional[str]:
    if report_type == ReportType.ATBP:
        match = _ATBP_SPEAKER_RE.search(markdown)
        return match.group(1).strip() if match is not None else None

    if report_type == ReportType.PRESIDENT_ADDRESS:
        minister = _extract_addenda_minister(markdown)
        if minister:
            return minister
        if not _MINISTRY_HEADING_RE.search(markdown):
            return "The President"
        return None

    if report_type == ReportType.MOTION:
        match = _ADJOURNMENT_MOVER_RE.search(markdown)
        return match.group(1).strip() if match is not None else None

    if report_type == ReportType.BILL:
        match = _BILL_PRESENTER_RE.search(markdown)
        return match.group(1).strip() if match is not None else None

    return None


def _strip_markdown_marks(text: str) -> str:
    return _MARKDOWN_MARKS_RE.sub("", text)


def _extract_markdown_title(markdown_content: str) -> Optional[str]:
    for line in markdown_content.splitlines()[:_MARKDOWN_TITLE_SCAN_LINES]:
        match = _MARKDOWN_TITLE_RE.search(line)
        if match is not None:
            candidate = match.group(1).strip()
            if candidate:
                return candidate
    return None


def _is_line_matching_title(line: str, candidate: str) -> bool:
    line = _QUOTE_MARKS_RE.sub("", line)
    candidate = _QUOTE_MARKS_RE.sub("", candidate)
    if f"{candidate}**" in line:
        return True

    if line.startswith("#"):
        heading = _strip_markdown_marks(line.lstrip("#").strip()).lower()
        if heading == _strip_markdown_marks(candidate).lower():
            return True

    stripped = _strip_markdown_marks(line).strip().lower()
    if stripped and stripped == _strip_markdown_marks(candidate).lower():
        return True

    normalized_line = _WHITESPACE_RE.sub("", stripped)
    normalized_candidate = _WHITESPACE_RE.sub("", _strip_markdown_marks(candidate).lower())
    if normalized_line and normalized_candidate and (
        normalized_line == normalized_candidate
        or (normalized_line.startswith(normalized_candidate) and len(normalized_candidate) > _PREFIX_TITLE_LENGTH_FLOOR)
        or (normalized_candidate.endswith(normalized_line) and len(normalized_line) >= _MIN_AFFIX_TITLE_LENGTH)
        or (normalized_line.endswith(normalized_candidate) and len(normalized_candidate) >= _MIN_AFFIX_TITLE_LENGTH)
    ):
        return True

    no_chair = _CHAIR_PREFIX_RE.sub("", stripped).strip()
    no_suffix = _TRAILING_PARENTHETICAL_RE.sub("", no_chair).strip()
    normalized_line_without_chair = _WHITESPACE_RE.sub("", no_suffix.lower())
    if normalized_line_without_chair and normalized_line_without_chair == normalized_candidate:
        return True

    return False


def _get_first_bold_line_start(markdown_content: str) -> Optional[int]:
    for line_index, line in enumerate(markdown_content.splitlines()):
        if line.startswith("**") and line.strip("* "):
            # NOTE: A bold label followed by text is the first speech, so parsing starts on the line before it.
            return line_index if _WHOLE_BOLD_LINE_RE.match(line.strip()) else line_index - 1
    return None


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

    markdown_title = fix_mojibake(_extract_markdown_title(markdown_content) or "")

    candidates = [candidate for candidate in [
        title,
        original_title_clean,
        f"{title} {subtitle}" if subtitle else None,
        markdown_title or None,
        _TRAILING_ACRONYM_RE.sub("", title) if _TRAILING_ACRONYM_RE.search(title) else None,
    ] if candidate]

    for line_index, line in enumerate(markdown_content.splitlines()):
        for candidate in candidates:
            if _is_line_matching_title(line, candidate):
                return line_index

    return _get_first_bold_line_start(markdown_content)


def _is_artifact_line(line: str) -> bool:
    if not line:
        return True
    if not line.strip("* _|"):
        return True
    if _TABLE_RULE_RE.match(line):
        return True
    if line.startswith("!["):
        return True
    if line == "﻿":
        return True
    return False


def _merge_wrapped_bold_lines(lines: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        label = _BOLD_ONLY_LINE_RE.match(line.strip())
        if label is not None and not label.group(1).rstrip().endswith(":") and label.group(1).count("(") > label.group(1).count(")"):
            following = index + 1
            while following < len(lines) and not lines[following].strip():
                following += 1
            if following < len(lines) and _BOLD_OPENING_RE.match(lines[following].lstrip()):
                merged.append(line.rstrip()[:-2] + " " + lines[following].lstrip()[2:])
                index = following + 1
                continue
        merged.append(line)
        index += 1
    return merged


def _parse_speeches(markdown: str, start_of_speech_line: int, report_type: str = "") -> list[ParsedSpeech]:
    current_speaker = None
    is_in_preamble = True
    speeches: list[ParsedSpeech] = []
    for line in _merge_wrapped_bold_lines(markdown.splitlines()[start_of_speech_line + 1 :]):
        parsed_line = line.strip()
        parsed_line = _LEADING_BOLD_ARTIFACT_RE.sub("", parsed_line)
        if _is_artifact_line(parsed_line):
            continue
        if "**" not in parsed_line:
            if _TIME_MARKER_RE.match(parsed_line):
                continue
            if _MARKDOWN_HEADING_RE.match(parsed_line):
                continue
            label_match = _PLAIN_ROLE_LABEL_RE.match(parsed_line)
            if label_match is not None:
                current_speaker = _LANGUAGE_NOTE_RE.sub("", label_match.group(1)).strip()
                is_in_preamble = False
                if label_match.group(2):
                    speeches.append(ParsedSpeech(speaker=current_speaker, transcript=label_match.group(2)))
                continue
            if is_in_preamble:
                continue
            speeches.append(ParsedSpeech(
                speaker=None if _PROCEDURAL_LINE_RE.match(parsed_line) else current_speaker,
                transcript=parsed_line,
            ))
            if _LIST_OPENER_RE.match(parsed_line):
                current_speaker = None
            continue

        bold_match = _BOLD_RUN_RE.search(parsed_line)
        if bold_match is not None:
            transcript = _LEADING_COLON_RE.sub("", parsed_line.split(bold_match.group(0))[-1].strip())
            if transcript.startswith("|"):
                continue
            raw_speaker = bold_match.group(0).replace("*", "").replace(":", "").strip()
            # NOTE: A bold line holding only a language note keeps its text so it stays a section annotation.
            raw_speaker = _LANGUAGE_NOTE_RE.sub("", raw_speaker).strip() or raw_speaker
            # NOTE: A chair annotation names who presides, not a speaker, so text after it continues the current speaker.
            if (_CHAIR_ANNOTATION_FULL_RE.fullmatch(raw_speaker)
                    or _CHAIR_ANNOTATION_PREFIX_RE.match(raw_speaker)):
                if _ALPHANUMERIC_RE.search(transcript) and current_speaker is not None:
                    speeches.append(ParsedSpeech(speaker=current_speaker, transcript=transcript))
                continue
            new_speaker = raw_speaker
            is_bold_ending_with_colon = bold_match.group(0).rstrip().endswith(":**")
            new_speaker = _QUESTION_NUMBER_PREFIX_RE.sub("", new_speaker)
            new_speaker = _UNSPACED_HONORIFIC_RE.sub(r"\1 \2", new_speaker)
            # NOTE: A bold drop cap, or in motions a bold line opening with a quote mark, continues the current speaker; the whole line is speech.
            is_drop_cap = bool(_DROP_CAP_RE.fullmatch(new_speaker)) and new_speaker != "Mr" and new_speaker != "Er" and new_speaker != "Ms" and new_speaker != "Dr"
            if is_drop_cap or (report_type == ReportType.MOTION and new_speaker[:1] in _OPENING_QUOTE_MARKS):
                prefix = parsed_line[: bold_match.start()]
                bold_text = bold_match.group(0).replace("*", "").strip()
                body = bold_text + transcript if is_drop_cap else f"{bold_text} {transcript}"
                if not is_in_preamble:
                    speeches.append(ParsedSpeech(speaker=current_speaker, transcript=(prefix + body).strip()))
                continue
            if _PROCEDURAL_STAGE_RE.match(new_speaker):
                continue
            if (
                "$" in new_speaker
                or "%" in new_speaker
                or not _LETTER_RE.search(new_speaker)
                or (len(new_speaker) > _MAX_SPEAKER_NAME_LENGTH and not _SPEAKER_HONORIFIC_RE.search(new_speaker))
            ):
                continue
            # NOTE: A section annotation resets the speaker, and the check must run before the section-title skip below.
            is_section_annotation = (
                bool(_PARENTHESISED_RE.match(new_speaker) or _ITALIC_HEADING_RE.match(new_speaker))
                and not _SPEAKER_HONORIFIC_RE.search(new_speaker)
            )
            if is_section_annotation:
                current_speaker = None
                if transcript:
                    speeches.append(ParsedSpeech(speaker=None, transcript=transcript))
                continue
            if (not transcript
                    and not _SPEAKER_HONORIFIC_RE.search(raw_speaker)
                    and (":" not in bold_match.group(0) or not is_bold_ending_with_colon)):
                if raw_speaker in _SECTION_BOUNDARY_HEADINGS:
                    current_speaker = None
                continue
            if new_speaker:
                current_speaker = new_speaker
                is_in_preamble = False
            if current_speaker is not None:
                speeches.append(ParsedSpeech(speaker=current_speaker, transcript=transcript))
            continue

        if not is_in_preamble:
            speeches.append(ParsedSpeech(
                speaker=None if _PROCEDURAL_LINE_RE.match(parsed_line) else current_speaker,
                transcript=parsed_line,
            ))
            if _LIST_OPENER_RE.match(parsed_line):
                current_speaker = None

    for speech in speeches:
        if (match := _LANGUAGE_NOTE_RE.match(speech.transcript)) is not None:
            speech.transcript = speech.transcript[match.end() :]
    return [speech for speech in speeches if speech.transcript.strip() != ""]


def get_speeches(markdown: str, start_of_speech_line: int, report_type: str) -> list[ParsedSpeech]:
    parsed_speeches = _parse_speeches(markdown, start_of_speech_line, report_type)
    speakers = _extract_mps_speaking(markdown)
    speech_type = _classify_speech_type(parsed_speeches, len(speakers))

    if speech_type == ParsedSpeechType.PARSED:
        if ((report_type == ReportType.PRESIDENT_ADDRESS or report_type == ReportType.ATBP)
                and not speakers
                and parsed_speeches
                and _is_section_header_speaker(parsed_speeches[0].speaker)):
            speaker = _extract_body_attribution(markdown, report_type)
            if speaker:
                body = _get_single_speaker_transcript(markdown, start_of_speech_line)
                return [ParsedSpeech(speaker=speaker, transcript=body)] if body else []
        return parsed_speeches

    if speech_type == ParsedSpeechType.SINGLE_SPEAKER:
        body = _get_single_speaker_transcript(markdown, start_of_speech_line)
        return [ParsedSpeech(speaker=speakers[0], transcript=body)] if body else []

    if speech_type == ParsedSpeechType.NO_SPEAKER:
        speaker = _extract_body_attribution(markdown, report_type)
        if speaker:
            body = _get_single_speaker_transcript(markdown, start_of_speech_line)
            return [ParsedSpeech(speaker=speaker, transcript=body)] if body else []

    return []
