import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from enums import ReportType, ReportVersion
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


_BOLD_MARKER = "**"

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

_NEWER_ADJOURNMENT_MOVER_RE = re.compile(
    r"[−–—‒\-]\s*\[(?:\()?((?:Mr|Mrs|Ms|Dr|Prof|Mdm|Assoc\s+Prof)[^]()]+)\)?\]",
    re.IGNORECASE,
)

_NEWER_BILL_PRESENTER_RE = re.compile(
    r"presented\s+by\s+(?:[^(;]*\(([^)]+)\)|([^(;.]+))",
    re.IGNORECASE,
)

_NEWER_SYSTEM_NAME_TRAILING_CHARS = ". "
_NEWER_SYSTEM_START_LINE = -1

_SPEAKER_HONORIFIC_RE = re.compile(
    r"\b(Mr|Mrs|Ms|Dr|Prof|Mdm|Assoc|Inche|Tuan|Haji|The|Er)\b"
)

_PROCEDURAL_STAGE_RE = re.compile(
    r"^(First|Second|Third)\s+Reading$|^Committee$|^,$|^Year$",
    re.IGNORECASE,
)

_TABLE_CAPTION_RE = re.compile(r"^_?Table\b")

_PROCEDURAL_LINE_ANCHORS = (
    r"Question (?:put,? and agreed to|proposed|again proposed)",
    r"Question put,? and negatived",
    r"Amendment, by leave, withdrawn",
    r"The sum of \$?[0-9,]+ .*ordered to stand part",  # Committee of Supply head
    r"Clauses? [0-9A-Za-z, to and]{1,30} ordered to stand part",
    r"Bill (?:accordingly )?read a (?:Second|Third|second|third) time",
    r"Bill reported without amendment",
    r"Bill considered in Committee",
    r"(?:(?:First|Second|Third) [Rr]esolution|Resolutions?) (?:to be )?reported",
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
    r"(?:The )?(?:Clause|Schedule)(?:, as amended,)? ordered to stand part",
    r"There being only one proposal, the Clerk",
    r"(?:Mr|Mdm|Madam) (?:Deputy )?Speaker,? _?went to the Chair",
    r"_?Then,? the Mace",
    r"Question negatived",
    r"Bill read the First time",
    r"With the consent of (?:Mr|Mdm|Madam) (?:Deputy )?Speaker",
    r"Question, put,? and agreed to",
    r"The Question having been proposed at",
    r"At the conclusion of .{1,60}?(?:Address|speech), Mr (?:SPEAKER|Speaker), preceded by",
    r"The (?:Assembly|House|Council) resumed its sitting",
    r"The following amendments? (?:also )?stood in the names? of",
    r"The time allotted for .{1,80}? having expired",
    r"Amendments? agreed to",
    r"[*+#]{1,2}\s*(?:The (?:amendments?|motion)(?:, [^:]{1,200},)? reads? as follows|Consequential amendments?:)",
    r"Amendments? made: In (?:page|line|clause)",
    r"(?:First|Second|Third|Fourth|Fifth|Sixth|New) Schedule(?:, as amended,)? ordered to stand part",
    r"Parts? [IVXL]+\b.{0,80}ordered to stand part",
    r"Bill reported with (?:an )?amendments?",
    r"Consideration of [Cc]lauses? [\dA-Za-z, ()]{1,30} postponed",
)
_QUESTION_DECISION_ANCHORS = (
    r"Question,? [\"“'‘]?That\b.*(?:\bput\b|, agreed to\.?$|,? and negatived\.?$)",
    r"(?:Main |Original )?Question,? as amended,? .*(?:\bput\b|accordingly)",
    r"Question on the [^.]{1,60}? (?:put\b|accordingly)",
    r"Question accordingly (?:agreed|aggreed|negatived)",
    r"Question put,? [\"“'‘]That\b",
    r"(?:Main |Original )Motion,? as amended,? agreed to",
)
_PROCEDURAL_LINE_RE = re.compile(r"^[\s*_]*(?:" + "|".join(_PROCEDURAL_LINE_ANCHORS + _QUESTION_DECISION_ANCHORS) + ")")

# NOTE: these procedural lines keep the current speaker, because the lines after them were often the mover's or the chair's own speech.
_TURN_KEEPING_PROCEDURAL_LINE_RE = re.compile(
    r"^[\s*_]*(?:Question (?:again )?proposed|\*\s*The same amendment|" + "|".join(_QUESTION_DECISION_ANCHORS) + ")"
)

_AMENDMENT_NOTE_RE = re.compile(
    r"^[\s_*]*(?:\(\d+\) )?In page \d+(?:, (?:after )?lines? [\d, and]+)?: (?:after|to|leave)"
    r"|^[\s_]*[*+#]{1,2}\s*The (?:[Mm]otion|amendment|same (?:motion|amendment)) (?:also )?stood in the names? of"
)
_FOOTNOTE_LINE_RE = re.compile(
    r"^(?!\*\s*(?:Cols?\b|Vol\b|\d))(?:\*(?!\*)|\+{1,2}|#(?=\S)|†|‡|\[\d{1,2}\])\s*\S"
    r"|^\d{1,2}\s+[A-Z](?!.*\s{3})"
)
_CLOSED_FOOTNOTE_START_RE = re.compile(
    r"^\(\d{1,2}\)\s|^The (?:motion|amendment|same (?:motion|amendment)) also stood in the names? of"
)
_MAX_CLOSED_FOOTNOTE_LINES = 10
_HORIZONTAL_RULE = "* * *"

_OATH_LINE_RE = re.compile(
    r"^(?!.*\b(?:I|[Ww]e|[Yy]ou|[Mm]y|[Oo]ur)\b)[\s_*]*[^?!\"“”\[\]]{0,250}?\b(?:took(?: and subscribed)? (?:the|an|his|her|their) Oath|made (?:an |the |his |her |their )?Affirmation)"
    r" of Allegiance\b[^.?!]{0,80}?[\s_*]*[.:]?[\s_*\-–—]*$"
)
_STAGE_DIRECTION_LINE_RE = re.compile(
    r"^[\s_*]*(?:Petition handed to the Clerk|Written [Ss]tatement by .{1,200}?Standing Order|Thereupon,? (?:the Clerk|a count)"
    r"|After (?:one|two|three) minutes?[\s_*]*[-–—]*[\s_*]*$|Certificate of Urgency signed by the President"
    r"|Members summoned into (?:the )?Chamber|\(?Whereupon\b|The Clerk (?:handed|then|read))"
)

_WHOLE_BRACKETED_LINE_RE = re.compile(r"^[\s_*]*\[(?:[^\[\]]|\[[^\[\]]*\])*\][\s_*.]*$")
# NOTE: a "Please refer" note must name a vernacular speech, because whole-line "[Please refer to ...]" rows in written answers are the minister's answer.
_VERNACULAR_NOTE_RE = re.compile(
    r"^[\s_*]*\[[\s_*]*(?:For\s*vernacular|Please\s*refer\s*to[^\]]*Vernacular)",
    re.IGNORECASE,
)
_STANDING_ORDER_NOTE_RE = re.compile(r"^[\s_*]*\[[\s_*]*Pursuant to Standing Order", re.IGNORECASE)
_CHAIR_NOTE_RE = re.compile(r"^[\s_*]*\[[^\[\]]*\bin the Chair[\s_*.]*\]", re.IGNORECASE)
_REACTION_NOTE_RE = re.compile(r"^[\s_*]*\[[\s_*]*(?:Laughter|Interruption)[\s_*.]*\]")
_SUPPLY_HEADER_NOTE_RE = re.compile(r"^[\s_*]*(?:Committee of Supply|Official Report) - [^\[\]]*[\s_*.]*$")
_CHAMBER_NOTE_RE = re.compile(
    r"^[\s_*\[(]*[^.?!;:\"“”\[\]]{0,250}?\b(?:left|entered) the Chamber"
    r"(?: and took his seat| to receive His Excellency)?[\s_*.)\]]*$"
)
_HOUSE_ROSE_NOTE_RE = re.compile(r"^[\s_*\[(]*The House rose\b[^.\[\]]{0,80}[\s_*.)\]]*$")
_COPIES_NOTE_RE = re.compile(
    r"^[\s_*\[(]*(?:Typed copies|Printed copies|Copies)\b(?: of [^\[\]]{1,150}?)?(?: accordingly)?"
    r" (?:handed in|distributed|circulated)(?: to (?:the )?Clerk(?: at the Table)?)?(?: and distributed)?"
    r"(?: to (?:[Hh]on\. |hon )?Members)?[\s_*.)\]]*$"
)

_ROSE_SUBJECT_WORD = r"(?:[A-Z(][\w.'’()-]*|and|hon|than|five|bin|binte|for)"
_PLAIN_STAGE_DIRECTION_RE = re.compile(
    r"^[\s_*]*(?=.*\b(?:Mr|Mrs|Ms|Mdm|Dr|Prof|Inche|Encik|Tuan|Dato|Members?|Minister)\b)"
    + _ROSE_SUBJECT_WORD + r"(?:,? " + _ROSE_SUBJECT_WORD + r")*"
    r" (?:rose(?: in (?:his|her|their) place)?(?: for their (?:dissent|abstention) to be recorded)?"
    r"|indicated (?:assent|dissent|agreement|for their (?:dissent|abstention) to be recorded)|resumed (?:his|her) seat)[\s_*]*[-–—.]*[\s_*]*$"
)
_LABELLED_STAGE_DIRECTION_RE = re.compile(
    r"^[\s_*]*(?:and \*\*[^*]+\*\* )?(?:again |later )?"
    r"(?:rose(?: in (?:his|her) place| and then resumed his seat)?|left the Chamber|entered the Chamber(?: and took his seat)?)"
    r"[\s_*]*[-–—.]*[\s_*]*(?:\[Interruption\])?[\s_*.]*$"
)
# NOTE: unlike "rose -", these end the turn: the unlabelled lines after them are procedural records, not the last speaker's words.
_LABELLED_TURN_ENDING_DIRECTION_RE = re.compile(
    r"^[\s_*]*(?:and \*\*[^*]+\*\* )?"
    r"(?:indicated (?:assent|dissent|agreement)|resumed (?:his|her) seat|_?went to the Chair(?: and sat down)?"
    r"|(?:, _?standing at the Table, )?_?(?:took(?: and subscribed)? (?:the|an|his|her) Oath|made (?:an |the )?Affirmation) of Allegiance)"
    r"[\s_*]*[-–—.]*[\s_*]*$"
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
_RESOLVED_LINE_RE = re.compile(r"^[\s*_]*Resolved(?:,|[\s*_]*$)")
_ADJOURNMENT_LINE_RE = re.compile(r"^[\s*_]*Adjourned accordingly")
_SENTENCE_END_RE = re.compile(r"\.[\s_*]*$")
_MAX_ADJOURNMENT_CONTINUATIONS = 6


_MARKDOWN_TITLE_SCAN_LINES = 12
_PREFIX_TITLE_LENGTH_FLOOR = 8
_MIN_AFFIX_TITLE_LENGTH = 10
_MAX_SPEAKER_NAME_LENGTH = 80
_OPENING_QUOTE_MARKS = "\"“'"

_SPEAKER_ROLE_WORD_RE = re.compile(r"\b(President|Speaker|Minister|Secretary|Deputy|Senior|Acting)\b", re.IGNORECASE)
_OFFICE_WORD_RE = re.compile(r"\b(?:Chairman|Clerk|Leader)\b")
_DEFINITE_ARTICLE = "The"
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
_REPORT_HEADER_FIELD_RE = re.compile(r"^\|?\s*(?:Parliament No|Session No|Volume No|Sitting No|Sitting Date|Section Name|Title|MPs? Speaking):\|")
_LINE_EDGE_MARKUP_RE = re.compile(r"^(?:#{1,6}|\|)\s*|\s*\|$")
_MARKUP_ONLY_CHARACTERS = "* _|-"
_EMPHASIS_MARK_CHARACTERS = "*_ "
_BOLD_RUN_RE = re.compile(r"((?:\*\*[^*]+?\*\*\s*)+)")
_LEADING_COLON_RE = re.compile(r"^:\s*")
_CHAIR_ANNOTATION_FULL_RE = re.compile(r"[\[(]?\s*.+?\s*in the [Cc]hair\s*[.\])]*")
_CHAIR_ANNOTATION_PREFIX_RE = re.compile(r"[\[(]\s*.+?\s*in the [Cc]hair\s*[.\])]")
_ALPHANUMERIC_RE = re.compile(r"[A-Za-z0-9]")
_LETTER_RE = re.compile(r"[A-Za-z]")
_PARENTHESIS_RE = re.compile(r"[()]")
_MISS_RE = re.compile(r"\bMiss\b")
_LIST_ENUMERATOR_RE = re.compile(r"\(\s*[A-Za-z]{1,4}\s*\)")
_QUESTION_NUMBER_PREFIX_RE = re.compile(r"^\d+\\?\.\s+")
_UNSPACED_HONORIFIC_RE = re.compile(r"^(Mr|Mrs|Ms|Dr|Prof|Mdm|The|BG|RAdm|Er)([A-Z])")
_DROP_CAP_RE = re.compile(r"[A-Za-z]{1,2}")
_PARENTHESISED_RE = re.compile(r"^\(.*\)$")
_HONOURABLE_MEMBERS_RE = re.compile(r"^(?:Some |The )?[Hh]on(?:ourable|\.)? Members?$")
_LOWERCASE_START_RE = re.compile(r"^[a-z]")
_STAGE_DIRECTION_VERB_RE = re.compile(r"^(?:indicated|rose|resumed|say|said|signified|left|entered|took|made|stood|went|remained|again|later|and)\b")
_ITALIC_HEADING_RE = re.compile(r"^_[^_].*_$")
_SENTENCE_FINAL_RE = re.compile(r"[.?!][\"'”’)\]_*]*$")
_BRACKET_SPAN_RE = re.compile(r"(?:(?<=\s)[_*]+|^[_*]+)?\[([^\[\]]{1,250})\](?:[_*]*\.)?(?:[_*]+(?=\s|$))?")
_BRACKET_INNER_EDGE_CHARACTERS = " _*."
_STAGE_DIRECTION_INNER_RE = re.compile(
    r"^(?:More |Loud )?(?:Applause|Laughter|Interruptions?|Pauses?|Silence)\b(?:[ .][^\[\]]{0,60})?$"
    r"|^[A-Z(][^\[\]]*\b(?:shown|distributed|circulated|handed(?: in| out| over)?)\b"
    r"|^(?:Mr|Mrs|Ms|Mdm|Madam|Dr|Prof|Assoc\.? Prof|Encik|Inche|Hon\.?|The|Some|An?)\b[^\[\]]{0,80}?"
    r"\b(?:interrupted|rose|entered the Chamber|left the Chamber|resumed (?:his|her) seat|took (?:his|her) seat|indicated|raised (?:his|her) hand|stood up|walked)\b"
    r"|^(?:and )?(?:resumed (?:his|her) seat|remained seated|entered the Chamber)"
    r"|^[Ii]ndicat(?:ing|ion)\b|^[Gg]esturing\b|^[Ss]how(?:ing|s)\b|^The hon\.? Member gestured"
)


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


def _extract_body_attribution(markdown: str, report_type: str, report_version: str) -> Optional[str]:
    is_newer_system = report_version == ReportVersion.SPRS3

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

    if is_newer_system and report_type == ReportType.MOTION:
        match = _NEWER_ADJOURNMENT_MOVER_RE.search(markdown)
        return match.group(1).strip().rstrip(_NEWER_SYSTEM_NAME_TRAILING_CHARS) if match is not None else None

    if is_newer_system and (report_type == ReportType.BILL or report_type == ReportType.BILL_INTRODUCTION):
        match = _NEWER_BILL_PRESENTER_RE.search(markdown)
        if match is None:
            return None
        presenter = match.group(1) if match.group(1) is not None else match.group(2)
        return presenter.strip().rstrip(_NEWER_SYSTEM_NAME_TRAILING_CHARS)

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
    report_type: str,
    report_version: str,
) -> Optional[int]:
    if report_version == ReportVersion.SPRS3:
        return _NEWER_SYSTEM_START_LINE

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


def _is_editorial_note(line: str) -> bool:
    language_note = _LANGUAGE_NOTE_RE.match(line)
    note = line[language_note.end():] if language_note is not None else line
    if _WHOLE_BRACKETED_LINE_RE.match(note) and (
        _VERNACULAR_NOTE_RE.match(note)
        or _STANDING_ORDER_NOTE_RE.match(note)
        or _CHAIR_NOTE_RE.match(note)
        or _REACTION_NOTE_RE.match(note)
    ):
        return True
    return bool(
        _SUPPLY_HEADER_NOTE_RE.match(line)
        or _CHAMBER_NOTE_RE.match(line)
        or _HOUSE_ROSE_NOTE_RE.match(line)
        or _COPIES_NOTE_RE.match(line)
    )


def _is_non_speech_line(line: str) -> bool:
    if _PROCEDURAL_LINE_RE.match(line):
        return True
    if _OATH_LINE_RE.match(line):
        return True
    if _STAGE_DIRECTION_LINE_RE.match(line):
        return True
    if _AMENDMENT_NOTE_RE.match(line):
        return True
    if _is_editorial_note(line):
        return True
    return bool(_PLAIN_STAGE_DIRECTION_RE.match(line))


def _is_turn_ending_line(line: str) -> bool:
    if _WHOLE_BRACKETED_LINE_RE.match(line) and _STANDING_ORDER_NOTE_RE.match(line):
        return True
    if _OATH_LINE_RE.match(line):
        return True
    if not _PROCEDURAL_LINE_RE.match(line):
        return False
    return not _TURN_KEEPING_PROCEDURAL_LINE_RE.match(line)


def _is_collapsed_non_speech_line(stripped: str, unmarked: str, is_body_started: bool) -> bool:
    if _RESOLVED_LINE_RE.match(unmarked):
        return False
    if not is_body_started and (_MARKDOWN_HEADING_RE.match(stripped) or _WHOLE_BOLD_LINE_RE.match(stripped)):
        return True
    return _is_non_speech_line(unmarked)


def _get_single_speaker_speeches(markdown: str, start_of_speech_line: int, speaker: str) -> list[ParsedSpeech]:
    speeches: list[ParsedSpeech] = []
    speaker_lines: list[str] = []
    is_body_started = False
    adjournment_continuations = 0
    for line in markdown.splitlines()[start_of_speech_line + 1:]:
        stripped = line.strip()
        if _REPORT_HEADER_FIELD_RE.match(stripped):
            continue
        unmarked = _LINE_EDGE_MARKUP_RE.sub("", stripped)
        if not unmarked.strip(_MARKUP_ONLY_CHARACTERS):
            continue
        if adjournment_continuations > 0:
            speeches[-1].transcript += " " + unmarked
            adjournment_continuations = 0 if _SENTENCE_END_RE.search(unmarked) else adjournment_continuations - 1
            continue
        if not _is_collapsed_non_speech_line(stripped, unmarked, is_body_started):
            is_body_started = True
            speaker_lines.append(unmarked)
            continue
        if speaker_lines:
            speeches.append(ParsedSpeech(speaker=speaker, transcript=" ".join(speaker_lines)))
            speaker_lines = []
        speeches.append(ParsedSpeech(speaker=None, transcript=unmarked))
        if _ADJOURNMENT_LINE_RE.match(unmarked) and not _SENTENCE_END_RE.search(unmarked):
            adjournment_continuations = _MAX_ADJOURNMENT_CONTINUATIONS
    if speaker_lines:
        speeches.append(ParsedSpeech(speaker=speaker, transcript=" ".join(speaker_lines)))
    return speeches


def _is_speaker_name(name: str) -> bool:
    honorifics = _SPEAKER_HONORIFIC_RE.findall(name)
    if not honorifics:
        return False
    if any(honorific != _DEFINITE_ARTICLE for honorific in honorifics):
        return True
    if "(" in name:
        return True
    return _SPEAKER_ROLE_WORD_RE.search(name) is not None or _OFFICE_WORD_RE.search(name) is not None


def _is_bold_mid_sentence(line: str) -> bool:
    bold_match = _BOLD_RUN_RE.search(line)
    if bold_match is None:
        return False
    bold_text = bold_match.group(0).replace("*", "").strip()
    if _SPEAKER_HONORIFIC_RE.search(bold_text) or _MISS_RE.search(bold_text) or _DROP_CAP_RE.fullmatch(bold_text):
        return False
    text_before_bold = _LIST_ENUMERATOR_RE.sub("", _LANGUAGE_NOTE_RE.sub("", line[: bold_match.start()]))
    return _LETTER_RE.search(text_before_bold) is not None


def _is_bold_without_letters(line: str) -> bool:
    bold_match = _BOLD_RUN_RE.search(line)
    if bold_match is None:
        return False
    bold_text = bold_match.group(0)
    return (
        _LETTER_RE.search(bold_text) is None
        and _PARENTHESIS_RE.search(bold_text) is None
        and _LETTER_RE.search(line) is not None
    )


def _is_honourable_members_phrase(line: str) -> bool:
    bold_match = _BOLD_RUN_RE.search(line)
    if bold_match is None:
        return False
    if line[: bold_match.start()].strip():
        return False
    if _HONOURABLE_MEMBERS_RE.match(bold_match.group(0).replace("*", "").strip()) is None:
        return False
    text_after_bold = line[bold_match.end():]
    return _LOWERCASE_START_RE.match(text_after_bold) is not None and _STAGE_DIRECTION_VERB_RE.match(text_after_bold) is None


def _is_closed_footnote_block(lines: list[str], block: list[int], is_closed: bool) -> bool:
    if not is_closed or len(block) > _MAX_CLOSED_FOOTNOTE_LINES:
        return False
    if any(_BOLD_OPENING_RE.match(lines[index].strip()) for index in block):
        return False
    first_line = lines[block[0]].strip()
    return _FOOTNOTE_LINE_RE.match(first_line) is not None or _CLOSED_FOOTNOTE_START_RE.match(first_line) is not None


def _get_footnote_line_indexes(lines: list[str]) -> set[int]:
    rule_indexes = [index for index, line in enumerate(lines) if line.strip() == _HORIZONTAL_RULE]
    footnote_line_indexes: set[int] = set()
    for position, rule_index in enumerate(rule_indexes):
        is_closed = position + 1 < len(rule_indexes)
        block_end = rule_indexes[position + 1] if is_closed else len(lines)
        block = [index for index in range(rule_index + 1, block_end) if lines[index].strip()]
        if not block:
            continue
        if _is_closed_footnote_block(lines, block, is_closed):
            footnote_line_indexes.update(block)
            continue
        for index in block:
            if _FOOTNOTE_LINE_RE.match(lines[index].strip()) is None:
                break
            footnote_line_indexes.add(index)
    return footnote_line_indexes


def _parse_speeches(markdown: str, start_of_speech_line: int, report_type: str = "") -> list[ParsedSpeech]:
    current_speaker = None
    is_in_preamble = True
    speeches: list[ParsedSpeech] = []
    lines = _merge_wrapped_bold_lines(markdown.splitlines()[start_of_speech_line + 1 :])
    footnote_line_indexes = _get_footnote_line_indexes(lines)
    for line_index, line in enumerate(lines):
        parsed_line = line.strip()
        parsed_line = _LEADING_BOLD_ARTIFACT_RE.sub("", parsed_line)
        if _is_artifact_line(parsed_line):
            continue
        if (
            "**" not in parsed_line
            or _is_bold_mid_sentence(parsed_line)
            or _is_bold_without_letters(parsed_line)
            or (current_speaker is not None and _is_honourable_members_phrase(parsed_line))
        ):
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
            # NOTE: a footnote between rules sits inside a speech, so it gets no speaker and the turn carries on after it.
            if line_index in footnote_line_indexes:
                speeches.append(ParsedSpeech(speaker=None, transcript=parsed_line))
                continue
            speeches.append(ParsedSpeech(
                speaker=None if _is_non_speech_line(parsed_line) else current_speaker,
                transcript=parsed_line,
            ))
            if _is_turn_ending_line(parsed_line):
                current_speaker = None
            continue

        bold_match = _BOLD_RUN_RE.search(parsed_line)
        if bold_match is not None:
            transcript = _LEADING_COLON_RE.sub("", parsed_line.split(bold_match.group(0))[-1].strip())
            # NOTE: a bold cell next to a pipe is a table row, not a label, so the whole line stays with the current speaker.
            if transcript.startswith("|") or "|" in parsed_line[: bold_match.start()]:
                if not is_in_preamble:
                    speeches.append(ParsedSpeech(speaker=current_speaker, transcript=parsed_line))
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
            if _TABLE_CAPTION_RE.match(new_speaker):
                continue
            if (
                "$" in new_speaker
                or "%" in new_speaker
                or not _LETTER_RE.search(new_speaker)
                or (len(new_speaker) > _MAX_SPEAKER_NAME_LENGTH and not _SPEAKER_HONORIFIC_RE.search(new_speaker))
            ):
                continue
            # NOTE: a parenthesised annotation resets the speaker but an italic subheading sits inside a speech; the check must run before the section-title skip below.
            is_parenthesised_annotation = _PARENTHESISED_RE.match(new_speaker) is not None
            is_section_annotation = (
                (is_parenthesised_annotation or _ITALIC_HEADING_RE.match(new_speaker) is not None)
                and not _SPEAKER_HONORIFIC_RE.search(new_speaker)
            )
            if is_section_annotation:
                if is_parenthesised_annotation:
                    current_speaker = None
                if transcript:
                    speeches.append(ParsedSpeech(speaker=current_speaker, transcript=transcript))
                continue
            if (not transcript.strip(_EMPHASIS_MARK_CHARACTERS)
                    and not _is_speaker_name(raw_speaker)
                    and (":" not in bold_match.group(0) or not is_bold_ending_with_colon)):
                if raw_speaker in _SECTION_BOUNDARY_HEADINGS:
                    current_speaker = None
                continue
            # NOTE: a bold name before "rose -" is a stage direction, not a speaker label, so the current speaker stays and the name stays in the text.
            is_turn_ending_direction = _LABELLED_TURN_ENDING_DIRECTION_RE.match(transcript) is not None
            if is_turn_ending_direction or _LABELLED_STAGE_DIRECTION_RE.match(transcript):
                is_in_preamble = False
                text_before_bold = parsed_line[: bold_match.start()]
                is_lead_with_letters = _LETTER_RE.search(text_before_bold) is not None
                if is_lead_with_letters and _SENTENCE_FINAL_RE.search(text_before_bold.strip()):
                    speeches.append(ParsedSpeech(speaker=current_speaker, transcript=text_before_bold.strip()))
                    is_lead_with_letters = False
                bold_text = bold_match.group(0).replace("*", "")
                name_separator = " " if bold_text != bold_text.rstrip() else ""
                direction_lead = text_before_bold if is_lead_with_letters else ""
                speeches.append(ParsedSpeech(speaker=None, transcript=direction_lead + bold_text.strip() + name_separator + transcript))
                if is_turn_ending_direction:
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
                speaker=None if _is_non_speech_line(parsed_line) else current_speaker,
                transcript=parsed_line,
            ))
            if _is_turn_ending_line(parsed_line):
                current_speaker = None

    for speech in speeches:
        if (match := _LANGUAGE_NOTE_RE.match(speech.transcript)) is not None:
            speech.transcript = speech.transcript[match.end() :]
    return [speech for speech in speeches if speech.transcript.strip() != ""]


def _split_stage_directions(speeches: list[ParsedSpeech]) -> list[ParsedSpeech]:
    split_speeches: list[ParsedSpeech] = []
    for speech in speeches:
        if speech.speaker is None:
            split_speeches.append(speech)
            continue
        direction_matches = [
            match for match in _BRACKET_SPAN_RE.finditer(speech.transcript)
            if _STAGE_DIRECTION_INNER_RE.match(match.group(1).strip(_BRACKET_INNER_EDGE_CHARACTERS)) is not None
        ]
        if not direction_matches:
            split_speeches.append(speech)
            continue
        position = 0
        for match in direction_matches:
            text_before = speech.transcript[position:match.start()].strip()
            if text_before:
                split_speeches.append(ParsedSpeech(speaker=speech.speaker, transcript=text_before))
            split_speeches.append(ParsedSpeech(speaker=None, transcript=match.group(0)))
            position = match.end()
        text_after = speech.transcript[position:].strip()
        if text_after:
            split_speeches.append(ParsedSpeech(speaker=speech.speaker, transcript=text_after))
    return split_speeches


def _get_unsplit_speeches(markdown: str, start_of_speech_line: int, report_type: str, report_version: str) -> list[ParsedSpeech]:
    parsed_speeches = _parse_speeches(markdown, start_of_speech_line, report_type)
    speakers = _extract_mps_speaking(markdown)
    speech_type = _classify_speech_type(parsed_speeches, len(speakers))

    if speech_type == ParsedSpeechType.PARSED:
        if ((report_type == ReportType.PRESIDENT_ADDRESS or report_type == ReportType.ATBP)
                and not speakers
                and parsed_speeches
                and _is_section_header_speaker(parsed_speeches[0].speaker)):
            speaker = _extract_body_attribution(markdown, report_type, report_version)
            if speaker:
                return _get_single_speaker_speeches(markdown, start_of_speech_line, speaker)
        return parsed_speeches

    if speech_type == ParsedSpeechType.SINGLE_SPEAKER:
        return _get_single_speaker_speeches(markdown, start_of_speech_line, speakers[0])

    if speech_type == ParsedSpeechType.NO_SPEAKER:
        speaker = _extract_body_attribution(markdown, report_type, report_version)
        if speaker:
            return _get_single_speaker_speeches(markdown, start_of_speech_line, speaker)

    return []


def get_speeches(markdown: str, start_of_speech_line: int, report_type: str, report_version: str) -> list[ParsedSpeech]:
    speeches = _split_stage_directions(_get_unsplit_speeches(markdown, start_of_speech_line, report_type, report_version))
    unmarked_speeches = [
        ParsedSpeech(speaker=speech.speaker, transcript=speech.transcript.replace(_BOLD_MARKER, ""))
        for speech in speeches
    ]
    return [speech for speech in unmarked_speeches if speech.transcript.strip() != ""]
