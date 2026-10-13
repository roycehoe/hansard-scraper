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
    PARSED = "PARSED"
    SINGLE_SPEAKER = "SINGLE_SPEAKER"
    MULTI_SPEAKER = "MULTI_SPEAKER"
    NO_SPEAKER = "NO_SPEAKER"


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

# language note "(In Mandarin)" / "(_In Malay_):", with any italic or bold marks and the colon after it
_LANGUAGE_NOTE_RE = re.compile(
    r"[_*]*\(\s*[_*]*\s*(?:in|dalam)\s+(?:Mandar\w+|Malay|English|Tamil|Hokkien|Cantonese|Teochew|Hakka)\s*[_*]*\s*\)[_*]*\s*:?\s*",
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

# Parliamentary procedural stage labels that appear bold in bills/committee reports but are not speakers
_PROCEDURAL_STAGE_RE = re.compile(
    r"^(First|Second|Third)\s+Reading$|^Committee$|^,$|^Year$",
    re.IGNORECASE,
)

# Plain lines that record procedure or the chair, not a member's words. Each starts the stripped line,
# after any leading "*", "_" or whitespace.
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
    r"Resolved(?:,|[\s*_]*$)",  # the bare word, or "Resolved, "That ..."" recording the resolution
    r"Order for Second Reading read",
    r"Order read for",
    r"Adjourned accordingly",
    r"Thereupon (?:Mr|Mdm) (?:Deputy )?Speaker",  # "... left the Chair"
    r"(?:Sitting|Debate) (?:according(?:ly)? )?(?:suspended|resumed)",
    r"Suspension of Sitting",
    r"resumed at \d",  # second half of a suspension line split over two rows
    r"\d{1,2}\.\d{2} [ap]\.?m\.? until \d|_\d{1,2}\.\d{2} [ap]\.?m\.? to \d",  # "_4.22 p.m. until 5.30 p.m._"
    r"[A-Z][a-z]+(?:-[a-z]+)? minutes? (?:past|to) [A-Z][a-z]+ o'clock",  # adjournment time, spelled out
    r"(?:Amendment|Notice of motion|Copies of [^.]{0,80}) handed in(?: to the Clerk| and distributed to hon\. Members)?\.?$",
    r"No Member rising",
    r"\*\s*The same amendment",  # editorial footnote under an amendment list
    r"The (?:House|Assembly|Council|Committee) divided",
    r"Division taken",
    r"The following amendments? stood on the Order Paper",
)
_PROCEDURAL_LINE_RE = re.compile(r"^[\s*_]*(?:" + "|".join(_PROCEDURAL_LINE_ANCHORS) + ")")

# Procedural lines that open a list: the resolution text and names after a bare "Resolved,", division
# names, Order Paper amendments. The lines after one are not the preceding member's, so current_speaker
# is reset until the next label.
_LIST_OPENER_RE = re.compile(
    r"^[\s*_]*(?:Resolved,?[\s*_]*$|The (?:House|Assembly|Council|Committee) divided|Division taken"
    r"|The following amendments? stood on the Order Paper)"
)

# A role label with a parenthesised name printed without bold at the start of a plain line (the markdown lost
# the bold marks): "The Minister for Education (Mr X) (for the Minister for Y): Sir, ...". A bare name label
# ("Mr Tan: ...") is not taken: too often it is a line quoted inside another member's speech.
_PLAIN_HONORIFIC = r"(?:Mr|Mrs|Ms|Miss|Mdm|Madam|Dr|Prof|Assoc\.? Prof|Inche|Encik|Tuan|Haji|Che|Er|BG|RAdm|LG|MG|COL)\.?"
_PLAIN_ROLE_WORD = r"(?:[A-Z][A-Za-z'’.,&-]*|of|for|the|and|to)"
_PLAIN_ROLE_LABEL_RE = re.compile(
    r"^(The (?=[^:()]*\b(?:Minister|Secretary|Chairman|President|Leader|Attorney|Speaker)\b)"
    + _PLAIN_ROLE_WORD + r"(?: " + _PLAIN_ROLE_WORD + r"){0,15} \(" + _PLAIN_HONORIFIC + r" [^()]{2,50}\)"
    r"(?:\s*\([^()]{1,100}\))*)\s*:\s*(.*)$"
)

# Bold headings that open a new section of business. The text after one is never the preceding member's,
# so skipping the heading resets current_speaker. Kept to an explicit list: other headings (budget and
# Address sub-headings) sit inside a member's speech.
_SECTION_BOUNDARY_HEADINGS = frozenset({
    "ADJOURNMENT",
    "ADJOURNMENT OF DEBATE",
    "ADJOURNMENT TO A DATE TO BE FIXED",
    "ADJOURNMENT SINE DIE",
    "REARRANGEMENT OF ORDER OF BUSINESS",
    "COMMITTEE OF SUPPLY",
})

# A line that is bold from end to end: a heading, not a "**Speaker:** text" label.
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
    """True if the name looks like a topic/section header, not a person."""
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
        return match.group(1).strip() if match is not None else None

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
        return match.group(1).strip() if match is not None else None

    if report_type == "bill":
        match = _BILL_PRESENTER_RE.search(markdown)
        return match.group(1).strip() if match is not None else None

    return None


def _strip_markdown_marks(text: str) -> str:
    return _MARKDOWN_MARKS_RE.sub("", text)


def _extract_markdown_title(markdown_content: str) -> Optional[str]:
    """Extract the Title field from the markdown header row, if present."""
    for line in markdown_content.splitlines()[:_MARKDOWN_TITLE_SCAN_LINES]:
        match = _MARKDOWN_TITLE_RE.search(line)
        if match is not None:
            candidate = match.group(1).strip()
            if candidate:
                return candidate
    return None


def _is_line_matching_title(line: str, candidate: str) -> bool:
    """Return True if the line matches the candidate title via any strategy."""
    # Quote marks appear in the markdown title but not the API title, or the reverse.
    line = _QUOTE_MARKS_RE.sub("", line)
    candidate = _QUOTE_MARKS_RE.sub("", candidate)
    # Strategy 1: closed bold (**title**) — old format with proper closing
    if f"{candidate}**" in line:
        return True

    # Strategy 2: markdown heading (# title) — new format (Parliament 12+)
    if line.startswith("#"):
        heading = _strip_markdown_marks(line.lstrip("#").strip()).lower()
        if heading == _strip_markdown_marks(candidate).lower():
            return True

    # Strategy 3: stripped content — italic, open bold, plain text (old format)
    stripped = _strip_markdown_marks(line).strip().lower()
    if stripped and stripped == _strip_markdown_marks(candidate).lower():
        return True

    # Strategy 4: whitespace-normalized — OCR-damaged spacing, continuation markers
    # (line startswith candidate), addenda/prefix mismatches (candidate endswith line), and lines with
    # a context prefix before the title (line endswith candidate, e.g. "[Chair] HEAD X").
    normalized_line = _WHITESPACE_RE.sub("", stripped)
    normalized_candidate = _WHITESPACE_RE.sub("", _strip_markdown_marks(candidate).lower())
    if normalized_line and normalized_candidate and (
        normalized_line == normalized_candidate
        or (normalized_line.startswith(normalized_candidate) and len(normalized_candidate) > _PREFIX_TITLE_LENGTH_FLOOR)
        or (normalized_candidate.endswith(normalized_line) and len(normalized_line) >= _MIN_AFFIX_TITLE_LENGTH)
        or (normalized_line.endswith(normalized_candidate) and len(normalized_candidate) >= _MIN_AFFIX_TITLE_LENGTH)
    ):
        return True

    # Strategy 5: strip chair-annotation prefix [X in the Chair] and trailing
    # parenthetical suffix before comparing — handles lines like
    # "**[Mr Speaker in the Chair] TITLE (Announcement by Mr Speaker)**"
    no_chair = _CHAIR_PREFIX_RE.sub("", stripped).strip()
    no_suffix = _TRAILING_PARENTHETICAL_RE.sub("", no_chair).strip()
    normalized_line_without_chair = _WHITESPACE_RE.sub("", no_suffix.lower())
    if normalized_line_without_chair and normalized_line_without_chair == normalized_candidate:
        return True

    return False


def _get_first_bold_line_start(markdown_content: str) -> Optional[int]:
    """Fallback when no line matches the title, e.g. "DEBATE ON PRESIDENT'S ADDRESS" whose body
    heading reads "PRESIDENT'S ADDRESS Debate on the Address (First Allotted Day)". A fully bold
    first line is a heading and stands in for the title line; a bold label followed by text is the
    first speech, so parsing starts on the line before it."""
    for line_index, line in enumerate(markdown_content.splitlines()):
        if line.startswith("**") and line.strip("* "):
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

    # Extract the title as written in the markdown header — may differ from the DB
    # title due to HTML entity artifacts, OCR noise, or data entry errors.
    markdown_title = fix_mojibake(_extract_markdown_title(markdown_content) or "")

    candidates = [candidate for candidate in [
        title,
        original_title_clean,
        f"{title} {subtitle}" if subtitle else None,
        markdown_title or None,
        # A trailing acronym can wrap onto its own line: "... TRAINING SUBSIDIES" / "(SPUR)"
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
    """Join a speaker label that wrapped onto two bold lines, such as
    "**The Minister of State for Education (Mr Gan Kim Yong) (for the Minister for**"
    followed by "**Education):** ...", so the whole label is one bold block."""
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
    is_in_preamble = True  # True until the first real bold speaker name is seen
    speeches: list[ParsedSpeech] = []
    for line in _merge_wrapped_bold_lines(markdown.splitlines()[start_of_speech_line + 1 :]):
        parsed_line = line.strip()
        parsed_line = _LEADING_BOLD_ARTIFACT_RE.sub("", parsed_line)  # strip leading **** artifacts (e.g. ****8.**Name**)
        if _is_artifact_line(parsed_line):
            continue
        if "**" not in parsed_line:
            if _TIME_MARKER_RE.match(parsed_line):
                continue  # skip procedural time markers (e.g. "4.26 pm", "3.30 p.m.")
            if _MARKDOWN_HEADING_RE.match(parsed_line):
                continue  # skip markdown section headings (e.g. "#### [Mr SPEAKER in the Chair]")
            label_match = _PLAIN_ROLE_LABEL_RE.match(parsed_line)
            if label_match is not None:
                current_speaker = _LANGUAGE_NOTE_RE.sub("", label_match.group(1)).strip()
                is_in_preamble = False
                if label_match.group(2):
                    speeches.append(ParsedSpeech(speaker=current_speaker, transcript=label_match.group(2)))
                continue
            if is_in_preamble:  # skip text before the first real speaker
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
                continue  # table row header ("**Header** | ...") — bold is a column label, not a speaker
            raw_speaker = bold_match.group(0).replace("*", "").replace(":", "").strip()
            raw_speaker = _LANGUAGE_NOTE_RE.sub("", raw_speaker).strip() or raw_speaker  # a note-only bold line stays a section annotation
            # A "[X in the Chair]" annotation, bare or followed by a heading in the same bold line
            # ("**[Mr Speaker in the Chair] BILL**"), records who presides; it is not a speaker, and
            # any text after it continues the current speaker. OCR can glue the words ("Speakerin the").
            if (_CHAIR_ANNOTATION_FULL_RE.fullmatch(raw_speaker)
                    or _CHAIR_ANNOTATION_PREFIX_RE.match(raw_speaker)):
                if _ALPHANUMERIC_RE.search(transcript) and current_speaker is not None:
                    speeches.append(ParsedSpeech(speaker=current_speaker, transcript=transcript))
                continue
            new_speaker = raw_speaker
            is_bold_ending_with_colon = bold_match.group(0).rstrip().endswith(":**")
            # Strip leading question-number prefix from oral-answer speaker names
            # e.g. "1\. Assoc. Prof. Paulin Tay Straughan" → "Assoc. Prof. Paulin Tay Straughan"
            new_speaker = _QUESTION_NUMBER_PREFIX_RE.sub("", new_speaker)
            # Fix OCR artifacts where space was dropped between honorific and name
            new_speaker = _UNSPACED_HONORIFIC_RE.sub(r"\1 \2", new_speaker)
            # A bold drop cap ("**E**very year ...") and, in motions, a bold line opening with a
            # quote mark (a headline or letter read into the record) continue the current speaker.
            # The whole line is speech, so the transcript keeps any list marker before the bold
            # ("(a) **C** onnected") and the bold text itself.
            is_drop_cap = bool(_DROP_CAP_RE.fullmatch(new_speaker)) and new_speaker not in ("Mr", "Er", "Ms", "Dr")
            if is_drop_cap or (report_type == "motion" and new_speaker[:1] in _OPENING_QUOTE_MARKS):
                prefix = parsed_line[: bold_match.start()]
                bold_text = bold_match.group(0).replace("*", "").strip()
                body = bold_text + transcript if is_drop_cap else f"{bold_text} {transcript}"
                if not is_in_preamble:
                    speeches.append(ParsedSpeech(speaker=current_speaker, transcript=(prefix + body).strip()))
                continue
            # Fix A: reject parliamentary procedural stage labels (e.g. "Third Reading:", "Committee:")
            # These end with a colon so the generic section-title skip misses them.
            if _PROCEDURAL_STAGE_RE.match(new_speaker):
                continue
            # Fix B: reject table/data content masquerading as a speaker name:
            #   - contains $ or % (budget/statistics column headers)
            #   - has no letter characters at all (punctuation-only artifacts like ",")
            #   - longer than 80 chars with no honorific (document-fragment headings)
            if (
                "$" in new_speaker
                or "%" in new_speaker
                or not _LETTER_RE.search(new_speaker)
                or (len(new_speaker) > _MAX_SPEAKER_NAME_LENGTH and not _SPEAKER_HONORIFIC_RE.search(new_speaker))
            ):
                continue
            # Paren-only annotations (e.g. "(Accidents and violations):") and italic
            # sub-section dividers (e.g. "_HDB Policy Changes_") are procedural cues,
            # not speaker changes. Reset current_speaker so following lines get speaker=None
            # until a real bold speaker name appears. Must run before the generic section-title
            # skip so that italic headings with no colon are also caught and reset.
            is_section_annotation = (
                bool(_PARENTHESISED_RE.match(new_speaker) or _ITALIC_HEADING_RE.match(new_speaker))
                and not _SPEAKER_HONORIFIC_RE.search(new_speaker)
            )
            if is_section_annotation:
                current_speaker = None
                if transcript:
                    speeches.append(ParsedSpeech(speaker=None, transcript=transcript))
                continue
            # Skip generic section-title lines: no honorific AND (no colon, or colon is mid-title
            # not at the end). Catches "**MINISTRY OF EDUCATION**", "**Table 1: Description**".
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
        # Old-format docs use bold section headers (e.g. **ASSENTS TO BILLS PASSED**,
        # **EXTERNAL ENVIRONMENT**) that _parse_speeches misidentifies as speakers.
        # When MPs Speaking is empty and the first parsed speaker looks like a
        # section header, collapse everything to a single correctly-attributed speech.
        if (report_type in ("president-address", "atbp")
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
