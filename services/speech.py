import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from enums import ReportType, ReportVersion, SpeechKind
from exceptions import HansardUnattributedSpeechError
from schemas.unattributed_speech import UnattributedSpeechRange
from utils.markdown_parser import (
    ASCII_FOLDED_CHARACTERS,
    PROC_TEXT_CLOSE_TAG,
    PROC_TEXT_OPEN_TAG,
)
from utils.text import fix_mojibake


@dataclass
class ParsedSpeech:
    speaker: Optional[str]
    transcript: str
    kind: SpeechKind


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
    r"\*\*[^*]+\*\*[ \t]*\n(?:[ \t]*\n)*"
    r"[ \t]*((?:Mr|Mrs|Ms|Dr|Prof\.?|Mdm|Assoc|RAdm|BG|LG|MG|COL)\s+[A-Z][A-Za-z '.()\-]+?)[ \t]*\n"
    r"(?:Minister|Deputy|Senior|Acting|Second|Secretary|Permanent|Political|Director|Prime)",
    re.MULTILINE | re.IGNORECASE,
)

_ADDENDA_TITLE_RE = re.compile(r"Title:\|\s*ADDENDA", re.IGNORECASE)
_ADDENDA_SIGNATURE_NAME_RE = re.compile(r"^[A-Z][A-Z .'\-]+$")
_ADDENDA_SIGNATURE_TITLE_RE = re.compile(r"^_[^_]*Minister[^_]*_$")

_MINISTRY_HEADING_RE = re.compile(
    r"\*\*[^\n*]*(?:MINISTRY|PRIME MINISTER)[^\n*]*\*\*",
    re.IGNORECASE,
)

_LANGUAGE_NOTE = r"[_*]*\(\s*[_*]*\s*(?:in|dalam)\s+(?:Mandar\w+|Malay|English|Tamil|Hokkien|Cantonese|Teochew|Hakka)\s*[_*]*\s*\)[_*]*"
_LANGUAGE_NOTE_RE = re.compile(_LANGUAGE_NOTE + r"\s*:?\s*", re.IGNORECASE)

_ADJOURNMENT_MOVER_RE = re.compile(
    r"[−–—\-]\s*\[((?:Mr|Mrs|Ms|Dr|Prof|Mdm|Assoc\s+Prof)[^]]+)\]",
    re.IGNORECASE,
)

_BILL_PRESENTER_RE = re.compile(
    r"presented\s+by[^(]*\(([^)]+)\)",
    re.IGNORECASE,
)

_FIRST_READING_RE = re.compile(
    r"\bpresented\s+(?:for\s+.{1,150}?\s+)?by\b.{1,400}?\bread\s+(?:for\s+)?(?:the|a)\s+First\s+time\b",
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
    r"\b(Mr|Mrs|Ms|Dr|Prof|Mdm|Assoc|Inche|Tuan|Haji|The|Er|Miss|Madam|Che)\b"
)
# NOTE: these titles count only at the start of a label, because a report title or an amendment note names members after them ("BG LEE HSIEN LOONG (Statement ...)").
_LEADING_TITLE_RE = re.compile(r"^(?:Encik|BG|MG|LG|COL|RAdm|Maj|Cdre|Tun|Dato)\b")

_PROCEDURAL_STAGE_RE = re.compile(
    r"^(First|Second|Third)\s+Reading$|^Committee$|^,$|^Year$",
    re.IGNORECASE,
)

_TABLE_CAPTION_RE = re.compile(r"^_?Table\b")

_BROUGHT_UP_ANCHOR = r"Brought up, and read the First [Tt]ime"
_DIVISION_RECORD_ANCHOR = r"(?:On question put, the|`?The) (?:[Hh]ouse|Assembly|Council|Committee) divided"
_DIVISION_LIST_HEADING_ANCHOR = r"Ayes\.?\s+Noes\.?$"
_DIVISION_RECORD_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=" + _DIVISION_RECORD_ANCHOR + ":)")
_PROCEDURAL_LINE_ANCHORS = (
    r"Question (?:put[.,]? and agreed to|proposed|again proposed)",
    r"Question put[.,]?[\s*_]*$",
    r"Question put,? and negatived",
    r"(?:Original |Main )?[Qq]uestion (?:again )?(?:put|proposed)[.,]?[\s*_]*$",
    r"(?:Original |Main )?[Qq]uestion put,? (?:and|an|arid|anti) (?:agreed|disagreed|negatived|resolved)",
    r"Question put: Ayes",
    r"Division [Bb]ells? rung",
    r"Motion made,? and Question proposed",
    r"Bill accordingly read the (?:Second|Third) time",
    r"Clause read a Second time and added to the Bill",
    r"A ?m{1,2}endments?(?: to the amendment)?,? by,? leave[.,]? [Ww]ithdrawn",
    r"The sum of \$?[0-9,]+ .*ordered to stand part",  # Committee of Supply head
    r"Clauses?_? [0-9A-Za-z_, to and]{1,30} ordered to stand part",
    r"Bill (?:accordingly )?read a (?:Second|Third|second|third) time",
    r"Bill reported,? without [Aa]mendment",
    r"Bill considered in Committee",
    r"(?:(?:First|Second|Third) [Rr]esolution|Resolutions?) (?:to be )?reported",
    r"Resolved(?:,|[\s*_]*$)",
    r"Order for Second Reading read",
    r"Order read for",
    r"Adjourned accordingly",
    r"Thereupon,? (?:Mr|Mdm) (?:Deputy )?(?:Speaker|SPEAKER)",
    r"(?:Sitting|Debate) (?:according(?:ly)? )?(?:suspended|resumed)",
    r"Suspension of Sitting",
    r"resumed at \d",  # second half of a split suspension line
    r"\d{1,2}\.\d{2} [ap]\.?m\.? until \d|_\d{1,2}\.\d{2} [ap]\.?m\.? to \d",
    r"[A-Z][a-z]+(?:-[a-z]+)? minutes? (?:past|to) [A-Z][a-z]+ o'clock",
    r"(?:Amendments?|Notice of motion|Copies of [^.]{0,80}) handed in(?: to the Clerk| and distributed to hon\. Members)?[.,]?$",
    r"No Member rising",
    r"\*\s*The same amendment",
    _DIVISION_RECORD_ANCHOR,
    _DIVISION_LIST_HEADING_ANCHOR,
    r"Division taken",
    r"The following amendments? stood on the Order Paper",
    r"(?:The )?(?:Clause|Schedule)_?(?:, as amended,)? ordered to stand part",
    r"There being only one proposal, the Clerk",
    r"(?:Mr|Mdm|Madam) (?:Deputy )?Speaker,? _?went to the Chair",
    r"_?Then,? the Mace",
    r"Question negatived",
    r"Bill (?:presented and )?read the First [Tt]ime",
    _BROUGHT_UP_ANCHOR,
    r"With the consent of (?:Mr|Mdm|Madam) (?:Deputy )?Speaker",
    r"Question, put,? and agreed to",
    r"The Question having been proposed at",
    r"At the conclusion of .{1,60}?(?:Address|speech), Mr (?:SPEAKER|Speaker), preceded by",
    r"The (?:Assembly|House|Council) resumed its sitting",
    r"The following amendments? (?:also )?stood in the names? of",
    r"The time allotted for .{1,80}? having expired",
    r"Amendments? (?:accordingly )?(?:agreed to|negatived)",
    r"[*+#]{1,2}\s*(?:The (?:amendments?|motion)(?:, [^:]{1,200},)? reads? as follows|Consequential amendments?:)",
    r"Amendments? made: In (?:page|line|clause)",
    r"(?:First|Second|Third|Fourth|Fifth|Sixth|New) Schedule(?:, as amended,)? ordered to stand part",
    r"Parts? [IVXL]+\b.{0,80}ordered to stand part",
    r"Bill reported,? with (?:an )?[Aa]mendments?",
    r"Consideration of [Cc]lauses? [\dA-Za-z, ()]{1,30} postponed",
)
_QUESTION_DECISION_ANCHORS = (
    r"Question_?[\s,.]{1,3}_?[\"“'‘]?That\b.*(?:(?:\b|_)put\b|, agreed to\.?$|,? and negatived\.?$)",
    r"(?:Main |Original )?Question,? as amended,? .*(?:\bput\b|accordingly)",
    r"Questions? on the [^.]{1,60}? (?:put\b|accordingly)",
    r"Question accordingly (?:agreed|aggreed|negatived)",
    r"Question put[.,]?\s*[\"“'‘]\s*That\b",
    r"(?:Main |Original )Motion,? as amended,? agreed to",
)
_PROCEDURAL_LINE_RE = re.compile(r"^[\s*_]*(?:" + "|".join(_PROCEDURAL_LINE_ANCHORS + _QUESTION_DECISION_ANCHORS) + ")")

# NOTE: these procedural lines keep the current speaker, because the lines after them were often the mover's or the chair's own speech.
_TURN_KEEPING_PROCEDURAL_LINE_RE = re.compile(
    r"^[\s*_]*(?:Question (?:again )?proposed|\*\s*The same amendment|" + _BROUGHT_UP_ANCHOR + "|" + "|".join(_QUESTION_DECISION_ANCHORS) + ")"
)

_AMENDMENT_TEXT_RE = re.compile(r"^[\s_*]*(?:\(\d+\) )?In page \d+(?:, (?:after )?lines? [\d, and]+)?: (?:after|to|leave)")
_STOOD_IN_NAMES_NOTE_RE = re.compile(
    r"^[\s_(]*[*+#]{1,2}\s*The (?:[Mm]otion|amendment|same (?:motion|amendment)) (?:also )?stood in the names? of"
)
_AMENDMENT_FOLLOWS_NOTE_RE = re.compile(
    r"^[\s*_]*[*+#]{1,2}\s*(?:The (?:amendments?|motion)(?:, [^:]{1,200},)? reads? as follows|Consequential amendments?:)"
)
_COPIES_LINE_RE = re.compile(r"^[\s*_]*Copies of ")
_SUPPLY_AMENDMENT_TEXT_RE = re.compile(r"^[\s_*]*(?:\(\d+\)\s*)?(?:\([^()]*\):?\s*)?That the (?:total )?sum\b.{0,40}\ballocated for Head\b")
_UNANCHORED_PROCEDURAL_LINE_RE = re.compile(
    r"^[\s_*]*(?:Order for Third Reading read|(?:The )?(?:House|Assembly|Council) (?:immediately )?resolved itself into (?:a )?Committee"
    r"|(?:(?:Original|Main) )?(?:Question|Bill(?:, as amended,)?)(?: accordingly)?,? (?:put|read (?:a|the) (?:First|Second|Third) time|reported)\b)"
)
_ORDER_PAPER_TEXT_RE = re.compile(
    r"^[\s_*]*(?:\d+\\?\.\s+)?To ask the (?:Prime )?Minister\b|^[\s_*]*[\"“]?That (?:this|the) (?:Assembly|House|Parliament|Council)\b"
)
_CLAUSE_CAPTION_RE = re.compile(r"^[\s_*]*(?:New )?Clauses? \d+[A-Z]?\s*[-–—]+\s*$")
_SUPPLY_HEAD_RE = re.compile(r"^[\s_*]*Head [A-Z]{0,2} ?\d+ ?[-–—]")
_FOOTNOTE_LINE_RE = re.compile(
    r"^(?!\*\s*(?:Cols?\b|Vol\b|\d))(?:\*(?!\*)|\+{1,2}|#(?=\S)|\^|†|‡|\[\d{1,2}\])\s*\S"
    r"|^\d{1,2}\s+[A-Z](?!.*\s{3})"
)
_CLOSED_FOOTNOTE_START_RE = re.compile(
    r"^\(\d{1,2}\)\s|^The (?:motion|amendment|same (?:motion|amendment)) also stood in the names? of"
)
_MAX_CLOSED_FOOTNOTE_LINES = 10
_MIN_SPEECH_LINE_LENGTH = 120
_SPEECH_START_RE = re.compile(r"^(?!In page\b|That\b)[A-Z]")
_FOOTNOTE_REFERENCE_RE = re.compile(r"\b(?:Appendix|Annex|cols?\.?|columns?|See|reproduced|Letter)\b", re.IGNORECASE)
_COLUMN_REFERENCE_NOTE_RE = re.compile(r"^[*#\s]*(?:Cols?|Vol)\b\.?(?:\s*\d|\s*$)|^\*\s*\d{3,5}-\d{3,5}\.?$")
_HORIZONTAL_RULE = "* * *"
_UNDERSCORE_RULE_RE = re.compile(r"^_{20,}$")

_OATH_LINE_RE = re.compile(
    r"^(?!.*\b(?:I|[Ww]e|[Yy]ou|[Mm]y|[Oo]ur)\b)[\s_*]*[^?!\"“”\[\]]{0,250}?\b(?:took(?: and subscribed)? (?:the|an|his|her|their) Oath|made (?:an |the |his |her |their )?Affirmation)"
    r" of Allegiance\b[^.?!]{0,80}?[\s_*]*[.:]?[\s_*\-–—]*$"
)
_PROCEDURAL_RECORD_LINE_RE = re.compile(
    r"^[\s_*]*(?:Petition handed to the Clerk|Thereupon,? (?:the Clerk|a count)"
    r"|After (?:one|two|three) minutes?[\s_*]*[-–—]*[\s_*]*$|Certificate of Urgency signed by the President"
    r"|Members summoned into (?:the )?Chamber|\(?Whereupon\b|The Clerk (?:handed|then|read))"
)
_WRITTEN_STATEMENT_NOTE_RE = re.compile(r"^[\s_*]*Written [Ss]tatement by .{1,200}?Standing Order")

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
_PLAIN_CHAMBER_EVENT_RE = re.compile(
    r"^[\s_*]*(?=.*\b(?:Mr|Mrs|Ms|Mdm|Dr|Prof|Inche|Encik|Tuan|Dato|Members?|Minister)\b)"
    + _ROSE_SUBJECT_WORD + r"(?:,? " + _ROSE_SUBJECT_WORD + r")*"
    r" (?:rose(?: in (?:his|her|their) place)?(?: for their (?:dissent|abstention) to be recorded)?"
    r"|indicated (?:assent|dissent|agreement|for their (?:dissent|abstention) to be recorded)|resumed (?:his|her) seat)[\s_*]*[-–—.]*[\s_*]*$"
)
_LABELLED_CHAMBER_EVENT_RE = re.compile(
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
_LABELLED_PROCEDURAL_DIRECTION_RE = re.compile(
    r"^[\s_*]*(?:and \*\*[^*]+\*\* )?"
    r"(?:_?went to the Chair|(?:, _?standing at the Table, )?_?(?:took(?: and subscribed)? (?:the|an|his|her) Oath|made (?:an |the )?Affirmation) of Allegiance)"
)

_PLAIN_HONORIFIC = r"(?:Mr|Mrs|Ms|Miss|Mdm|Madam|Dr|Prof|Assoc\.? Prof|Inche|Encik|Tuan|Haji|Che|Er|BG|RAdm|LG|MG|COL)\.?"
_PLAIN_ROLE_WORD = r"(?:[A-Z][A-Za-z'’.,&-]*|of|for|the|and|to)"
_PLAIN_ROLE = (
    r"The (?=[^:()]*\b(?:Minister|Secretary|Chairman|President|Leader|Attorney|Speaker)\b)"
    + _PLAIN_ROLE_WORD + r"(?: " + _PLAIN_ROLE_WORD + r"){0,15}"
)
# NOTE: A bare name label such as "Mr Tan:" is not matched: it is often a line quoted inside another speech.
_PLAIN_ROLE_LABEL_RE = re.compile(
    r"^(" + _PLAIN_ROLE + r" \(" + _PLAIN_HONORIFIC + r" [^()]{2,50}\)"
    r"(?:\s*\([^()]{1,100}\))*)\s*:\s*(.*)$"
)
# NOTE: a quoted line never carries a language note, so a bare name or an office without a name is a label when the note and a colon follow it; the optional ")" is a stray bracket the source prints after an office.
_PLAIN_LANGUAGE_NOTE_LABEL_RE = re.compile(
    r"^((?:" + _PLAIN_HONORIFIC + r" [A-Z][\w.'’-]*(?: [\w.'’-]+){0,7}"
    r"|" + _PLAIN_ROLE + r"(?:\)?\s*\(" + _PLAIN_HONORIFIC + r" [^()]{2,50}\))?)"
    r"(?:\s*\([^()]{2,60}\))?\s*(?i:" + _LANGUAGE_NOTE + r"))\s*:\s*(.*)$"
)

# NOTE: the chair's own label is matched bare, unlike "Mr Tan:", because in the newer system no quoted line opens with it and its call starts the chair's turn.
_PLAIN_CHAIR_LABEL_RE = re.compile(r"^((?:Mr|Mdm|Madam) (?:Deputy )?Speaker)\s*:\s*(.*)$")

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
_PROC_TEXT_LINE_RE = re.compile(r"^([_*]*)" + re.escape(PROC_TEXT_OPEN_TAG) + r"(.*)" + re.escape(PROC_TEXT_CLOSE_TAG) + r"([_*]*)$")
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
_TIME_MARKER_RE = re.compile(r"^\d{1,2}(?:\s*[.:]\s*\d{2})?\s*(?:[ap]\.?m|noon|midnight)\.?$", re.IGNORECASE)
_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}(\s|$)")
_REPORT_HEADER_FIELD_RE = re.compile(r"^\|?\s*(?:Parliament No|Session No|Volume No|Sitting No|Sitting Date|Section Name|Title|MPs? Speaking):\|")
_LINE_EDGE_MARKUP_RE = re.compile(r"^(?:#{1,6}|\|)\s*|\s*\|$")
_MARKUP_ONLY_CHARACTERS = "* _|-"
_EMPHASIS_MARK_CHARACTERS = "*_ "
_BOLD_RUN_RE = re.compile(r"((?:\*\*[^*]+?\*\*\s*)+)")
_LEADING_COLON_RE = re.compile(r"^:\s*")
_PERSONAL_TITLE_RE = re.compile(r"^(?:Mr|Mrs|Ms|Dr|Prof|Mdm|Miss|Madam|Assoc ?Prof|Encik|Inche|Haji|Tuan|Tun|Che|Er)\b")
_PARENTHESISED_GROUP_RE = re.compile(r"\([^)]*\)?")
_NAME_PARTICLES = frozenset({"bin", "binte", "binti", "bte", "bt", "b", "s/o", "d/o", "a/l", "a/p", "van", "de", "der", "di"})
_REPORTING_VERBS = frozenset({"asked", "says", "said", "echoes", "raised", "stood", "remained"})
_MIN_FRAGMENT_LOWERCASE_WORDS = 2
_COLLECTIVE_LABEL_RE = re.compile(r"\b(?:hon\.?|Members?|Speaker|Chairman|Chair|Clerk|Interpreter)\b", re.IGNORECASE)
_CONTINUATION_NOTE_RE = re.compile(r"^_?\(cont", re.IGNORECASE)
_QUESTION_NUMBER_ONLY_RE = re.compile(r"^\d+\s*$")
_BRACKETED_BOLD_OPENINGS = ("**[", "**(")
_OPENING_PARENTHESIS = "("
_CLOSING_PARENTHESIS = ")"
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
_CHAMBER_EVENT_VERB_RE = re.compile(r"^(?:indicated|rose|resumed|say|said|signified|left|entered|took|made|stood|went|remained|again|later|and)\b")
_QUESTION_LEAD_IN_RE = re.compile(r"^The following questions? stood in the name of\s+(?:\*\*[^*]+\*\*\s*)+[–—-]*$")
_PLAIN_QUESTION_LEAD_IN_RE = re.compile(r"^The following [Qq]uestions? stood in the name of\s+([A-Z][^*]*?)\s*:?[–—-]*$")
_TRAILING_DASH_RE = re.compile(r"\s*[–—-]+$")
_ITALIC_HEADING_RE = re.compile(r"^_[^_].*_$")
_MAX_ITALIC_TITLE_LENGTH = 150
_ITALIC_TITLE_RE = re.compile(rf"^_[^_\n]{{1,{_MAX_ITALIC_TITLE_LENGTH}}}(?<!!)_$")
_SENTENCE_FINAL_RE = re.compile(r"[.?!][\"'”’)\]_*]*$")
_BRACKET_SPAN_RE = re.compile(r"(?:(?<=\s)[_*]+|^[_*]+)?\[([^\[\]]{1,250})\](?:[_*]*\.)?(?:[_*]+(?=\s|$))?")
_BRACKET_INNER_EDGE_CHARACTERS = " _*."
_EVENT_FULL_STOP_RE = re.compile(r"\][_*]*(\.)[_*]*$")
_EMPTY_EMPHASIS_TAIL_RE = re.compile(r"(?<=\])(?:__|\*\*)$")
_AUDIENCE_EVENT_PATTERN = r"(?i:(?:more |loud )?(?:applause|laughter|interruptions?|interjections?|pauses?|silence|background noise)\b(?:[ .][^\[\]]{0,60})?$)"
_DOCUMENT_ACTION_PATTERN = (
    r"(?:[A-Z(]"
    r"|(?=[^\[\]]*(?:(?i:\b(?:hon\.? members?|members?|house|screen|slides?|handouts?|photos?|charts?|cop(?:y|ies))\b)|\b(?:Mr|Mdm|Mrs|Ms|Dr|Prof) [A-Z])))"
    r"[^\[\]]*\b(?:shown|showed|distributed|circulated|handed(?: in| out| over)?|displayed)\b"
)
_MEMBER_ACTION_PATTERN = (
    r"(?:Mr|Mrs|Ms|Mdm|Madam|Dr|Prof|Assoc\.? Prof|Encik|Inche|[Hh]on\.?|[Tt]he hon\.?|The|Some|An?|Members?)\b[^\[\]]{0,80}?"
    r"\b(?:interrupted|interjected|rose|enters? the Chamber|entered the Chamber|left the Chamber|resumed (?:his|her) seat|took (?:his|her) seat"
    r"|indicated|raised (?:his|her) hand|stood up|walked|holds? up|pointed|gestured|waved|nodded)\b"
)
_SEAT_ACTION_PATTERN = r"(?:and )?(?:resumed (?:his|her) seat|remained seated|entered the Chamber)"
_HON_MEMBERS_ACTION_PATTERN = r"[Hh]on\.? Members?\b[^\[\]]{0,250}?\b(?:say|proposed|raised their hands)\b"
_GESTURE_PATTERN = r"(?i:(?:and )?(?:indicat(?:ing|ion)|gestur(?:ing|ed)|pointing|pointed|showing|shows|exhibiting|holds? up|holding up|waving|displaying)\b)"
_CHAMBER_EVENT_INNER_RE = re.compile(
    "^(?:" + "|".join((_AUDIENCE_EVENT_PATTERN, _DOCUMENT_ACTION_PATTERN, _MEMBER_ACTION_PATTERN, _SEAT_ACTION_PATTERN, _HON_MEMBERS_ACTION_PATTERN, _GESTURE_PATTERN)) + ")"
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
    if _has_speaker_honorific(stripped):
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
        if _ADDENDA_TITLE_RE.search(markdown) is not None:
            return None
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
    line = _QUOTE_MARKS_RE.sub("", line.translate(ASCII_FOLDED_CHARACTERS))
    candidate = _QUOTE_MARKS_RE.sub("", candidate.translate(ASCII_FOLDED_CHARACTERS))
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


def _split_division_records(lines: list[str]) -> list[str]:
    # NOTE: the source prints the record right after the member's words with no paragraph break, so the converter joined them into one line.
    return [part for line in lines for part in _DIVISION_RECORD_SPLIT_RE.split(line)]


def _get_bracketed_note_kind(note: str) -> Optional[SpeechKind]:
    if _WHOLE_BRACKETED_LINE_RE.match(note) is None:
        return None
    if _VERNACULAR_NOTE_RE.match(note) is not None or _STANDING_ORDER_NOTE_RE.match(note) is not None:
        return SpeechKind.EDITORIAL_NOTE
    if _CHAIR_NOTE_RE.match(note) is not None:
        return SpeechKind.PROCEDURAL
    if _REACTION_NOTE_RE.match(note) is not None:
        return SpeechKind.CHAMBER_EVENT
    return None


def _get_note_kind(line: str) -> Optional[SpeechKind]:
    language_note = _LANGUAGE_NOTE_RE.match(line)
    bracketed_note_kind = _get_bracketed_note_kind(line[language_note.end():] if language_note is not None else line)
    if bracketed_note_kind is not None:
        return bracketed_note_kind
    if _SUPPLY_HEADER_NOTE_RE.match(line) is not None:
        return SpeechKind.HEADING
    if _HOUSE_ROSE_NOTE_RE.match(line) is not None:
        return SpeechKind.PROCEDURAL
    if _CHAMBER_NOTE_RE.match(line) is not None or _COPIES_NOTE_RE.match(line) is not None:
        return SpeechKind.CHAMBER_EVENT
    return None


def _get_non_speech_kind(line: str) -> Optional[SpeechKind]:
    if _AMENDMENT_TEXT_RE.match(line) is not None:
        return SpeechKind.DOCUMENT_TEXT
    if _STOOD_IN_NAMES_NOTE_RE.match(line) is not None or _WRITTEN_STATEMENT_NOTE_RE.match(line) is not None:
        return SpeechKind.EDITORIAL_NOTE
    note_kind = _get_note_kind(line)
    if note_kind is not None:
        return note_kind
    if _PLAIN_CHAMBER_EVENT_RE.match(line) is not None:
        return SpeechKind.CHAMBER_EVENT
    if _OATH_LINE_RE.match(line) is not None or _PROCEDURAL_RECORD_LINE_RE.match(line) is not None:
        return SpeechKind.PROCEDURAL
    if _PROCEDURAL_LINE_RE.match(line) is None:
        return None
    if _AMENDMENT_FOLLOWS_NOTE_RE.match(line) is not None:
        return SpeechKind.EDITORIAL_NOTE
    if _COPIES_LINE_RE.match(line) is not None:
        return SpeechKind.CHAMBER_EVENT
    return SpeechKind.PROCEDURAL


def _get_no_speaker_kind(line: str) -> SpeechKind:
    non_speech_kind = _get_non_speech_kind(line)
    if non_speech_kind is not None:
        return non_speech_kind
    if _SUPPLY_AMENDMENT_TEXT_RE.match(line) is not None or _ORDER_PAPER_TEXT_RE.match(line) is not None:
        return SpeechKind.DOCUMENT_TEXT
    if _UNANCHORED_PROCEDURAL_LINE_RE.match(line) is not None:
        return SpeechKind.PROCEDURAL
    if _SUPPLY_HEAD_RE.match(line) is not None or _CLAUSE_CAPTION_RE.match(line) is not None:
        return SpeechKind.HEADING
    return SpeechKind.UNCLASSIFIED


def _build_current_speaker_speech(current_speaker: Optional[str], transcript: str) -> ParsedSpeech:
    if _ITALIC_TITLE_RE.match(transcript) is not None:
        return ParsedSpeech(speaker=None, transcript=transcript, kind=SpeechKind.HEADING)
    if current_speaker is None:
        return ParsedSpeech(speaker=None, transcript=transcript, kind=_get_no_speaker_kind(transcript))
    return ParsedSpeech(speaker=current_speaker, transcript=transcript, kind=SpeechKind.SPEECH)


def _build_line_speech(line: str, current_speaker: Optional[str]) -> ParsedSpeech:
    non_speech_kind = _get_non_speech_kind(line)
    if non_speech_kind is not None:
        return ParsedSpeech(speaker=None, transcript=line, kind=non_speech_kind)
    return _build_current_speaker_speech(current_speaker, line)


def _build_footnote_speech(line: str) -> ParsedSpeech:
    is_document_text = _AMENDMENT_TEXT_RE.match(line) is not None or _SUPPLY_AMENDMENT_TEXT_RE.match(line) is not None
    kind = SpeechKind.DOCUMENT_TEXT if is_document_text else SpeechKind.EDITORIAL_NOTE
    return ParsedSpeech(speaker=None, transcript=line, kind=kind)


def _is_turn_ending_line(line: str) -> bool:
    if _WHOLE_BRACKETED_LINE_RE.match(line) and _STANDING_ORDER_NOTE_RE.match(line):
        return True
    if _OATH_LINE_RE.match(line):
        return True
    if not _PROCEDURAL_LINE_RE.match(line):
        return False
    return not _TURN_KEEPING_PROCEDURAL_LINE_RE.match(line)


def _get_proc_text(line: str) -> Optional[str]:
    match = _PROC_TEXT_LINE_RE.match(line)
    if match is None:
        return None
    return match.group(1) + match.group(2).strip() + match.group(3)


def _is_first_reading_formula(line: str) -> bool:
    if _FIRST_READING_RE.search(line) is None:
        return False
    return not line.startswith(_BOLD_MARKER) or _WHOLE_BOLD_LINE_RE.match(line) is not None


def _is_first_reading_lead_line(stripped: str, unmarked: str) -> bool:
    return (
        _TIME_MARKER_RE.match(unmarked.strip(_EMPHASIS_MARK_CHARACTERS)) is not None
        or _MARKDOWN_HEADING_RE.match(stripped) is not None
        or _WHOLE_BOLD_LINE_RE.match(stripped) is not None
        or _SENTENCE_END_RE.search(unmarked) is None
        or not unmarked[:1].isupper()
    )


def _build_speaker_lines_speeches(speaker: str, speaker_lines: list[str]) -> list[ParsedSpeech]:
    transcript = " ".join(speaker_lines)
    if _TIME_MARKER_RE.match(transcript):
        return []
    return [ParsedSpeech(speaker=speaker, transcript=transcript, kind=SpeechKind.SPEECH)]


def _get_single_speaker_speeches(markdown: str, start_of_speech_line: int, speaker: str) -> list[ParsedSpeech]:
    speeches: list[ParsedSpeech] = []
    speaker_lines: list[str] = []
    is_body_started = False
    adjournment_continuations = 0
    trailing_lead_line_count = 0
    for line in markdown.splitlines()[start_of_speech_line + 1:]:
        stripped = line.strip()
        if _REPORT_HEADER_FIELD_RE.match(stripped):
            continue
        edge_unmarked = _LINE_EDGE_MARKUP_RE.sub("", stripped)
        if not edge_unmarked.strip(_MARKUP_ONLY_CHARACTERS):
            continue
        proc_text = _get_proc_text(edge_unmarked)
        unmarked = edge_unmarked if proc_text is None else proc_text
        is_first_reading = proc_text is None and _FIRST_READING_RE.search(unmarked) is not None
        if adjournment_continuations > 0:
            speeches[-1].transcript += " " + unmarked
            adjournment_continuations = 0 if _SENTENCE_END_RE.search(unmarked) else adjournment_continuations - 1
            continue
        is_resolved_line = _RESOLVED_LINE_RE.match(unmarked) is not None
        if not is_body_started and not is_resolved_line and (_MARKDOWN_HEADING_RE.match(stripped) or _WHOLE_BOLD_LINE_RE.match(stripped)):
            continue
        non_speech_kind = _get_non_speech_kind(unmarked)
        if is_resolved_line or non_speech_kind is None:
            is_body_started = True
            if proc_text is None and not is_first_reading:
                speaker_lines.append(unmarked)
                trailing_lead_line_count = trailing_lead_line_count + 1 if _is_first_reading_lead_line(stripped, unmarked) else 0
                continue
        # NOTE: only the bill's title quote, and the time stamp and heading just before it, belong to the first reading, so they join its row; earlier lines are speech.
        if is_first_reading:
            lead_start = len(speaker_lines) - trailing_lead_line_count
            unmarked = " ".join(speaker_lines[lead_start:] + [unmarked])
            speaker_lines = speaker_lines[:lead_start]
        trailing_lead_line_count = 0
        if speaker_lines:
            speeches.extend(_build_speaker_lines_speeches(speaker, speaker_lines))
            speaker_lines = []
        speeches.append(ParsedSpeech(speaker=None, transcript=unmarked, kind=SpeechKind.PROCEDURAL if proc_text is not None or is_first_reading else non_speech_kind))
        if _ADJOURNMENT_LINE_RE.match(unmarked) and not _SENTENCE_END_RE.search(unmarked):
            adjournment_continuations = _MAX_ADJOURNMENT_CONTINUATIONS
    if speaker_lines:
        speeches.extend(_build_speaker_lines_speeches(speaker, speaker_lines))
    return speeches


def _has_speaker_honorific(text: str) -> bool:
    return _SPEAKER_HONORIFIC_RE.search(text) is not None or _LEADING_TITLE_RE.match(text) is not None


def _is_speaker_name(name: str) -> bool:
    honorifics = _SPEAKER_HONORIFIC_RE.findall(name)
    if _LEADING_TITLE_RE.match(name) is not None:
        return True
    if not honorifics:
        return False
    if any(honorific != _DEFINITE_ARTICLE for honorific in honorifics):
        return True
    if "(" in name:
        return True
    return _SPEAKER_ROLE_WORD_RE.search(name) is not None or _OFFICE_WORD_RE.search(name) is not None


def _is_name_fragment(label: str) -> bool:
    if _PERSONAL_TITLE_RE.match(label) is None:
        return False
    words = _PARENTHESISED_GROUP_RE.sub("", label).split()[1:]
    lowercase_words = [word for word in words if word[:1].islower() and word not in _NAME_PARTICLES]
    return len(lowercase_words) >= _MIN_FRAGMENT_LOWERCASE_WORDS or any(word in _REPORTING_VERBS or word.endswith("'s") for word in words)


def _is_person_label_before_pipe(parsed_line: str, bold_match: re.Match) -> bool:
    label = bold_match.group(0).replace(_BOLD_MARKER, "").strip()
    after_label = parsed_line[bold_match.end() :].lstrip()
    if "|" in parsed_line[: bold_match.end()] or after_label.startswith("|"):
        return False
    if not label.endswith(":") and not after_label.startswith(":"):
        return False
    return _is_speaker_name(label.removesuffix(":").strip())


def _is_bold_mid_sentence(line: str) -> bool:
    bold_match = _BOLD_RUN_RE.search(line)
    if bold_match is None:
        return False
    bold_text = bold_match.group(0).replace("*", "").strip()
    if _has_speaker_honorific(bold_text) or _MISS_RE.search(bold_text) or _DROP_CAP_RE.fullmatch(bold_text):
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
    return _LOWERCASE_START_RE.match(text_after_bold) is not None and _CHAMBER_EVENT_VERB_RE.match(text_after_bold) is None


def _is_note_line(line: str) -> bool:
    return (
        _FOOTNOTE_LINE_RE.match(line) is not None
        or _CLOSED_FOOTNOTE_START_RE.match(line) is not None
        or _COLUMN_REFERENCE_NOTE_RE.match(line) is not None
    )


def _is_closed_footnote_block(lines: list[str], block: list[int], is_closed: bool) -> bool:
    if not is_closed or len(block) > _MAX_CLOSED_FOOTNOTE_LINES:
        return False
    if any(_BOLD_OPENING_RE.match(lines[index].strip()) for index in block):
        return False
    first_line = lines[block[0]].strip()
    # NOTE: a column reference is a whole note, so what follows it may be unlabelled speech; its block is read line by line instead.
    return _is_note_line(first_line) and _COLUMN_REFERENCE_NOTE_RE.match(first_line) is None


def _get_speech_start_position(lines: list[str], block: list[int]) -> int:
    # NOTE: a page-bottom footnote is followed by the next page's speech before the next rule, so a long paragraph right after a finished note is speech.
    for position, index in enumerate(block):
        line = lines[index].strip()
        if _is_note_line(line):
            continue
        previous_line = lines[block[position - 1]].strip() if position > 0 else ""
        is_after_finished_note = _COLUMN_REFERENCE_NOTE_RE.match(previous_line) is not None or (
            _SENTENCE_END_RE.search(previous_line) is not None and _FOOTNOTE_REFERENCE_RE.search(previous_line) is None
        )
        is_speech = len(line) >= _MIN_SPEECH_LINE_LENGTH and _SPEECH_START_RE.match(line) is not None and is_after_finished_note
        return position if is_speech else len(block)
    return len(block)


def _get_footnote_line_indexes(lines: list[str]) -> set[int]:
    rule_indexes = [index for index, line in enumerate(lines) if line.strip() == _HORIZONTAL_RULE or _UNDERSCORE_RULE_RE.match(line.strip()) is not None]
    footnote_line_indexes: set[int] = set()
    for position, rule_index in enumerate(rule_indexes):
        is_closed = position + 1 < len(rule_indexes)
        block_end = rule_indexes[position + 1] if is_closed else len(lines)
        block = [index for index in range(rule_index + 1, block_end) if lines[index].strip()]
        if not block:
            continue
        if _is_closed_footnote_block(lines, block, is_closed):
            footnote_line_indexes.update(block[: _get_speech_start_position(lines, block)])
            continue
        for index in block:
            if not _is_note_line(lines[index].strip()):
                break
            footnote_line_indexes.add(index)
    return footnote_line_indexes


def _is_preamble_title_line(line: str) -> bool:
    return (
        _REPORT_HEADER_FIELD_RE.match(line) is not None
        or line.startswith(_BOLD_MARKER)
        or _PARENTHESISED_RE.match(line.strip(_EMPHASIS_MARK_CHARACTERS)) is not None
        or _ITALIC_HEADING_RE.match(line) is not None
    )


def _get_plain_label_match(line: str, report_version: str) -> Optional[re.Match]:
    role_label_match = _PLAIN_ROLE_LABEL_RE.match(line)
    if role_label_match is not None:
        return role_label_match
    if report_version == ReportVersion.SPRS3:
        chair_label_match = _PLAIN_CHAIR_LABEL_RE.match(line)
        if chair_label_match is not None:
            return chair_label_match
    return _PLAIN_LANGUAGE_NOTE_LABEL_RE.match(line)


def _parse_speeches(markdown: str, start_of_speech_line: int, report_type: str, report_version: str) -> list[ParsedSpeech]:
    current_speaker = None
    is_in_preamble = True
    preamble_speeches: list[ParsedSpeech] = []
    speeches: list[ParsedSpeech] = []
    lines = _split_division_records(_merge_wrapped_bold_lines(markdown.splitlines()[start_of_speech_line + 1 :]))
    footnote_line_indexes = _get_footnote_line_indexes(lines)
    for line_index, line in enumerate(lines):
        parsed_line = line.strip()
        parsed_line = _LEADING_BOLD_ARTIFACT_RE.sub("", parsed_line)
        if _is_artifact_line(parsed_line):
            continue
        proc_text = _get_proc_text(parsed_line)
        # NOTE: the older system does not tag a first reading, so its formula stands in for the tag.
        is_first_reading_formula = proc_text is None and _is_first_reading_formula(parsed_line)
        if is_first_reading_formula:
            proc_text = parsed_line
        # NOTE: the source tags this block as a step in the House's business, so it gets no speaker; the turn ends exactly as the untagged line would end it.
        if proc_text is not None:
            if not is_in_preamble or is_first_reading_formula or not _is_preamble_title_line(proc_text):
                (preamble_speeches if is_in_preamble else speeches).append(
                    ParsedSpeech(speaker=None, transcript=proc_text, kind=SpeechKind.PROCEDURAL)
                )
            if not is_in_preamble and _is_turn_ending_line(proc_text):
                current_speaker = None
            continue
        if _TIME_MARKER_RE.match(parsed_line.strip(_EMPHASIS_MARK_CHARACTERS)):
            continue
        if (
            "**" not in parsed_line
            or _is_bold_mid_sentence(parsed_line)
            or _is_bold_without_letters(parsed_line)
            or (current_speaker is not None and _is_honourable_members_phrase(parsed_line))
        ):
            if _MARKDOWN_HEADING_RE.match(parsed_line):
                continue
            plain_lead_in_match = _PLAIN_QUESTION_LEAD_IN_RE.match(parsed_line)
            if plain_lead_in_match is not None:
                (preamble_speeches if is_in_preamble else speeches).append(ParsedSpeech(speaker=None, transcript=parsed_line, kind=SpeechKind.PROCEDURAL))
                current_speaker = plain_lead_in_match.group(1)
                is_in_preamble = False
                continue
            label_match = _get_plain_label_match(parsed_line, report_version)
            if label_match is not None:
                current_speaker = _LANGUAGE_NOTE_RE.sub("", label_match.group(1)).strip()
                is_in_preamble = False
                if label_match.group(2):
                    speeches.append(_build_current_speaker_speech(current_speaker, label_match.group(2)))
                continue
            if is_in_preamble:
                if not _is_preamble_title_line(parsed_line):
                    preamble_speeches.append(ParsedSpeech(speaker=None, transcript=parsed_line, kind=_get_no_speaker_kind(parsed_line)))
                continue
            # NOTE: a footnote between rules sits inside a speech, so it gets no speaker and the turn carries on after it.
            if line_index in footnote_line_indexes:
                speeches.append(_build_footnote_speech(parsed_line))
                continue
            speeches.append(_build_line_speech(parsed_line, current_speaker))
            if _is_turn_ending_line(parsed_line):
                current_speaker = None
            continue

        bold_match = _BOLD_RUN_RE.search(parsed_line)
        if bold_match is not None:
            unbolded_line = parsed_line.replace(_BOLD_MARKER, "").strip()
            # NOTE: the source splits a bracketed chair annotation into several bold runs, so only the whole line shows it is no label.
            if parsed_line.startswith(_BRACKETED_BOLD_OPENINGS) and _CHAIR_ANNOTATION_FULL_RE.fullmatch(unbolded_line) is not None:
                continue
            transcript = _LEADING_COLON_RE.sub("", parsed_line.split(bold_match.group(0))[-1].strip())
            # NOTE: a bold cell next to a pipe is a table row, not a label, so the whole line stays with the current speaker; a person's label with a colon may still have a pipe in its speech.
            if "|" in parsed_line and not _is_person_label_before_pipe(parsed_line, bold_match):
                if not is_in_preamble:
                    speeches.append(_build_current_speaker_speech(current_speaker, parsed_line))
                continue
            raw_speaker = bold_match.group(0).replace("*", "").replace(":", "").strip()
            speaker_without_note = _LANGUAGE_NOTE_RE.sub("", raw_speaker).strip()
            is_language_note_line = speaker_without_note == "" and transcript == ""
            # NOTE: A bold line holding only a language note keeps its text so it stays a section annotation.
            raw_speaker = speaker_without_note or raw_speaker
            # NOTE: the lead-in sentence stands outside the bold name and a dash follows it, so the generic split would drop the sentence and keep the dash in the label.
            if report_version == ReportVersion.SPRS3 and _QUESTION_LEAD_IN_RE.match(parsed_line) is not None:
                (preamble_speeches if is_in_preamble else speeches).append(ParsedSpeech(speaker=None, transcript=unbolded_line, kind=SpeechKind.PROCEDURAL))
                current_speaker = _TRAILING_DASH_RE.sub("", raw_speaker)
                is_in_preamble = False
                continue
            # NOTE: the source bolds a label up to the constituency's last word and leaves its closing bracket outside the bold, or drops it.
            if raw_speaker.count(_OPENING_PARENTHESIS) > raw_speaker.count(_CLOSING_PARENTHESIS):
                raw_speaker += _CLOSING_PARENTHESIS
                transcript = _LEADING_COLON_RE.sub("", transcript.removeprefix(_CLOSING_PARENTHESIS).lstrip())
            # NOTE: A chair annotation names who presides, not a speaker, so text after it continues the current speaker.
            if (_CHAIR_ANNOTATION_FULL_RE.fullmatch(raw_speaker)
                    or _CHAIR_ANNOTATION_PREFIX_RE.match(raw_speaker)):
                if _ALPHANUMERIC_RE.search(transcript) and current_speaker is not None:
                    speeches.append(_build_current_speaker_speech(current_speaker, transcript))
                continue
            # NOTE: a bold name with a verb after it opens a sentence about that member, so the whole line is the current speaker's speech.
            if current_speaker is not None and _is_name_fragment(raw_speaker):
                speeches.append(_build_current_speaker_speech(current_speaker, unbolded_line))
                continue
            is_non_label_bold = (
                not _is_speaker_name(raw_speaker)
                and _PERSONAL_TITLE_RE.match(raw_speaker) is None
                and _COLLECTIVE_LABEL_RE.search(raw_speaker) is None
            )
            is_bold_ending_with_colon = bold_match.group(0).rstrip().endswith(":**")
            is_heading_line = (
                (_MARKDOWN_HEADING_RE.match(parsed_line) is not None and bool(transcript))
                or _CONTINUATION_NOTE_RE.match(transcript) is not None
                or (is_bold_ending_with_colon and not transcript.strip(_EMPHASIS_MARK_CHARACTERS))
            )
            non_speech_kind = _get_non_speech_kind(unbolded_line)
            is_question_stub = _QUESTION_NUMBER_ONLY_RE.match(parsed_line[: bold_match.start()]) is not None
            # NOTE: a bold heading, a bold word inside a procedural line or a question's "To ask" is no label; its text keeps a row with no speaker.
            if is_non_label_bold and (is_heading_line or non_speech_kind is not None or is_question_stub):
                # NOTE: a numbered bold phrase that is no label, such as a question's "To ask", stays in the current turn.
                if is_question_stub and non_speech_kind is None and current_speaker is not None:
                    speeches.append(_build_current_speaker_speech(current_speaker, unbolded_line))
                    continue
                if non_speech_kind is not None:
                    kind = non_speech_kind
                elif is_heading_line:
                    kind = SpeechKind.HEADING
                else:
                    kind = _get_no_speaker_kind(unbolded_line)
                (preamble_speeches if is_in_preamble else speeches).append(ParsedSpeech(speaker=None, transcript=unbolded_line, kind=kind))
                if non_speech_kind is not None and not is_in_preamble and _is_turn_ending_line(unbolded_line):
                    current_speaker = None
                continue
            new_speaker = raw_speaker
            new_speaker = _QUESTION_NUMBER_PREFIX_RE.sub("", new_speaker)
            new_speaker = _UNSPACED_HONORIFIC_RE.sub(r"\1 \2", new_speaker)
            # NOTE: A bold drop cap, or in motions a bold line opening with a quote mark, continues the current speaker; the whole line is speech.
            is_drop_cap = bool(_DROP_CAP_RE.fullmatch(new_speaker)) and new_speaker != "Mr" and new_speaker != "Er" and new_speaker != "Ms" and new_speaker != "Dr"
            if is_drop_cap or (report_type == ReportType.MOTION and new_speaker[:1] in _OPENING_QUOTE_MARKS):
                prefix = parsed_line[: bold_match.start()]
                bold_text = bold_match.group(0).replace("*", "").strip()
                body = bold_text + transcript if is_drop_cap else f"{bold_text} {transcript}"
                (preamble_speeches if is_in_preamble else speeches).append(
                    _build_current_speaker_speech(current_speaker, (prefix + body).strip())
                )
                continue
            if _PROCEDURAL_STAGE_RE.match(new_speaker):
                continue
            if _TABLE_CAPTION_RE.match(new_speaker):
                if report_version == ReportVersion.SPRS2:
                    (preamble_speeches if is_in_preamble else speeches).append(ParsedSpeech(speaker=None, transcript=_MARKDOWN_HEADING_RE.sub("", unbolded_line), kind=SpeechKind.HEADING))
                continue
            if (
                "$" in new_speaker
                or "%" in new_speaker
                or not _LETTER_RE.search(new_speaker)
                or (len(new_speaker) > _MAX_SPEAKER_NAME_LENGTH and not _has_speaker_honorific(new_speaker))
            ):
                continue
            # NOTE: a parenthesised annotation resets the speaker but an italic subheading sits inside a speech; the check must run before the section-title skip below.
            is_parenthesised_annotation = _PARENTHESISED_RE.match(new_speaker) is not None
            is_section_annotation = (
                (is_parenthesised_annotation or _ITALIC_HEADING_RE.match(new_speaker) is not None)
                and not _has_speaker_honorific(new_speaker)
            )
            # NOTE: in the older system a bold line that is only a language note says how the speaker goes on, so the speaker stays.
            is_speaker_kept = is_language_note_line and report_version == ReportVersion.SPRS2
            if is_section_annotation:
                if is_parenthesised_annotation and not is_speaker_kept:
                    current_speaker = None
                if transcript:
                    (preamble_speeches if is_in_preamble else speeches).append(_build_current_speaker_speech(current_speaker, transcript))
                continue
            if (not transcript.strip(_EMPHASIS_MARK_CHARACTERS)
                    and not _is_speaker_name(raw_speaker)
                    and (":" not in bold_match.group(0) or not is_bold_ending_with_colon)):
                if raw_speaker in _SECTION_BOUNDARY_HEADINGS:
                    current_speaker = None
                continue
            # NOTE: a bold name before "rose -" is a chamber event, not a speaker label, so the current speaker stays and the name stays in the text.
            is_turn_ending_direction = _LABELLED_TURN_ENDING_DIRECTION_RE.match(transcript) is not None
            if is_turn_ending_direction or _LABELLED_CHAMBER_EVENT_RE.match(transcript):
                is_in_preamble = False
                text_before_bold = parsed_line[: bold_match.start()]
                has_lead_letters = _LETTER_RE.search(text_before_bold) is not None
                is_lead_sentence = has_lead_letters and _SENTENCE_FINAL_RE.search(text_before_bold.strip()) is not None
                if is_lead_sentence:
                    speeches.append(_build_current_speaker_speech(current_speaker, text_before_bold.strip()))
                bold_text = bold_match.group(0).replace("*", "")
                name_separator = " " if bold_text != bold_text.rstrip() else ""
                direction_lead = text_before_bold if has_lead_letters and not is_lead_sentence else ""
                is_procedural_direction = _LABELLED_PROCEDURAL_DIRECTION_RE.match(transcript) is not None
                speeches.append(ParsedSpeech(
                    speaker=None,
                    transcript=direction_lead + bold_text.strip() + name_separator + transcript,
                    kind=SpeechKind.PROCEDURAL if is_procedural_direction else SpeechKind.CHAMBER_EVENT,
                ))
                if is_turn_ending_direction:
                    current_speaker = None
                continue
            if new_speaker:
                current_speaker = new_speaker
                is_in_preamble = False
            if current_speaker is not None:
                speeches.append(_build_current_speaker_speech(current_speaker, transcript))
            continue

        if is_in_preamble and _is_preamble_title_line(parsed_line):
            continue
        (preamble_speeches if is_in_preamble else speeches).append(_build_line_speech(parsed_line, current_speaker))
        if _is_turn_ending_line(parsed_line):
            current_speaker = None

    # NOTE: text before the first speaker keeps its row only when a speaker follows; a report with no label at all falls through to the single-speaker path.
    if not is_in_preamble:
        speeches = preamble_speeches + speeches
    for speech in speeches:
        if (match := _LANGUAGE_NOTE_RE.match(speech.transcript)) is not None:
            speech.transcript = speech.transcript[match.end() :]
    return [speech for speech in speeches if speech.transcript.strip() != ""]


def _split_speech_at_chamber_events(speech: ParsedSpeech) -> list[ParsedSpeech]:
    event_matches = [
        match for match in _BRACKET_SPAN_RE.finditer(speech.transcript)
        if _CHAMBER_EVENT_INNER_RE.match(match.group(1).strip(_BRACKET_INNER_EDGE_CHARACTERS)) is not None
    ]
    if not event_matches:
        return [speech]
    parts: list[tuple[str, bool]] = []
    position = 0
    for match in event_matches:
        parts.append((speech.transcript[position:match.start()], False))
        parts.append((match.group(0), True))
        position = match.end()
    parts.append((speech.transcript[position:], False))
    paragraph_parts: list[str] = []
    event_rows: list[ParsedSpeech] = []
    for text, is_event in parts:
        full_stop = _EVENT_FULL_STOP_RE.search(text) if is_event else None
        # NOTE: a full stop after the brackets ends the sentence the event cut, so it goes back to the paragraph unless that already ends one.
        is_full_stop_returned = full_stop is not None and bool(paragraph_parts) and _SENTENCE_FINAL_RE.search(paragraph_parts[-1]) is None
        if is_full_stop_returned:
            paragraph_parts[-1] += "."
            event_text = _EMPTY_EMPHASIS_TAIL_RE.sub("", text[: full_stop.start(1)] + text[full_stop.end(1):])
            event_rows.append(ParsedSpeech(speaker=None, transcript=event_text, kind=SpeechKind.CHAMBER_EVENT))
        elif is_event:
            event_rows.append(ParsedSpeech(speaker=None, transcript=text, kind=SpeechKind.CHAMBER_EVENT))
        # NOTE: punctuation left after an event ("[Interruption]-") belongs to the interrupted speech, so it stays on the event row.
        elif event_rows and _ALPHANUMERIC_RE.search(text) is None:
            event_rows[-1].transcript += text.rstrip()
        elif text.strip():
            paragraph_parts.append(text.strip())
    if not paragraph_parts:
        return event_rows
    # NOTE: the paragraph stays whole so no sentence is cut; the events follow it, so their place inside it is lost.
    return [ParsedSpeech(speaker=speech.speaker, transcript=" ".join(paragraph_parts), kind=speech.kind), *event_rows]


def _split_chamber_events(speeches: list[ParsedSpeech]) -> list[ParsedSpeech]:
    return [
        row
        for speech in speeches
        for row in ([speech] if speech.speaker is None else _split_speech_at_chamber_events(speech))
    ]


def _get_unlabelled_speeches(markdown: str, start_of_speech_line: int) -> list[ParsedSpeech]:
    speeches: list[ParsedSpeech] = []
    for line in markdown.splitlines()[start_of_speech_line + 1:]:
        stripped = line.strip()
        if _REPORT_HEADER_FIELD_RE.match(stripped):
            continue
        edge_unmarked = _LINE_EDGE_MARKUP_RE.sub("", stripped)
        if not edge_unmarked.strip(_MARKUP_ONLY_CHARACTERS):
            continue
        proc_text = _get_proc_text(edge_unmarked)
        if proc_text is not None:
            speeches.append(ParsedSpeech(speaker=None, transcript=proc_text, kind=SpeechKind.PROCEDURAL))
            continue
        kind = _get_no_speaker_kind(edge_unmarked)
        speeches.append(ParsedSpeech(speaker=None, transcript=edge_unmarked, kind=SpeechKind.DOCUMENT_TEXT if kind == SpeechKind.UNCLASSIFIED else kind))
    return speeches


def _get_fallback_speaker_from_parsed(
    markdown: str, parsed_speeches: list[ParsedSpeech], speakers: list[str], report_type: str, report_version: str
) -> Optional[str]:
    speech_type = _classify_speech_type(parsed_speeches, len(speakers))
    if speech_type == ParsedSpeechType.SINGLE_SPEAKER:
        return speakers[0]
    if speech_type == ParsedSpeechType.NO_SPEAKER:
        return _extract_body_attribution(markdown, report_type, report_version) or None
    if speech_type != ParsedSpeechType.PARSED:
        return None
    first_speaker = next((speech.speaker for speech in parsed_speeches if speech.speaker is not None), None)
    if ((report_type == ReportType.PRESIDENT_ADDRESS or report_type == ReportType.ATBP)
            and not speakers
            and first_speaker is not None
            and _is_section_header_speaker(first_speaker)):
        return _extract_body_attribution(markdown, report_type, report_version) or None
    return None


def get_fallback_speaker(markdown: str, start_of_speech_line: int, report_type: str, report_version: str) -> Optional[str]:
    parsed_speeches = _parse_speeches(markdown, start_of_speech_line, report_type, report_version)
    return _get_fallback_speaker_from_parsed(markdown, parsed_speeches, _extract_mps_speaking(markdown), report_type, report_version)


def _is_addenda_signature(speeches: list[ParsedSpeech], index: int) -> bool:
    return (
        index + 1 < len(speeches)
        and _ADDENDA_SIGNATURE_NAME_RE.match(speeches[index].transcript) is not None
        and _ADDENDA_SIGNATURE_TITLE_RE.match(speeches[index + 1].transcript) is not None
    )


# NOTE: an Addendum signed by several ministers prints each name under the part it closes, so a part is credited back from its signature.
def _credit_addenda_signers(speeches: list[ParsedSpeech]) -> list[ParsedSpeech]:
    signature_indexes = [index for index in range(len(speeches)) if _is_addenda_signature(speeches, index)]
    credited = list(speeches)
    part_start = 0
    for signature_index in signature_indexes:
        signer = speeches[signature_index].transcript
        for index in range(part_start, signature_index):
            speech = speeches[index]
            if speech.transcript != speech.transcript.upper():
                credited[index] = ParsedSpeech(speaker=signer, transcript=speech.transcript, kind=SpeechKind.SPEECH)
        part_start = signature_index + 2
    return credited


def _get_unsplit_speeches(markdown: str, start_of_speech_line: int, report_type: str, report_version: str) -> list[ParsedSpeech]:
    parsed_speeches = _parse_speeches(markdown, start_of_speech_line, report_type, report_version)
    speakers = _extract_mps_speaking(markdown)
    fallback_speaker = _get_fallback_speaker_from_parsed(markdown, parsed_speeches, speakers, report_type, report_version)
    if fallback_speaker is not None:
        return _get_single_speaker_speeches(markdown, start_of_speech_line, fallback_speaker)
    if parsed_speeches:
        return parsed_speeches
    if report_type == ReportType.PRESIDENT_ADDRESS:
        return _credit_addenda_signers(_get_unlabelled_speeches(markdown, start_of_speech_line))
    return _get_unlabelled_speeches(markdown, start_of_speech_line)


def get_speeches(markdown: str, start_of_speech_line: int, report_type: str, report_version: str) -> list[ParsedSpeech]:
    speeches = _split_chamber_events(_get_unsplit_speeches(markdown, start_of_speech_line, report_type, report_version))
    unmarked_speeches = [
        ParsedSpeech(speaker=speech.speaker, transcript=speech.transcript.replace(_BOLD_MARKER, "").strip(), kind=speech.kind)
        for speech in speeches
    ]
    return [speech for speech in unmarked_speeches if speech.transcript != ""]


def _get_unattributed_range_start(speeches: list[ParsedSpeech], speech_range: UnattributedSpeechRange) -> int:
    for index, speech in enumerate(speeches):
        if speech.speaker == speech_range.speaker and speech.transcript.startswith(speech_range.first_transcript_start):
            return index
    raise HansardUnattributedSpeechError(f"Report {speech_range.report_id}: no row starts with {speech_range.first_transcript_start!r}")


def _get_unattributed_range_end(speeches: list[ParsedSpeech], speech_range: UnattributedSpeechRange, start: int) -> int:
    for index in range(start, len(speeches)):
        speech = speeches[index]
        if speech.speaker == speech_range.speaker and speech.transcript.startswith(speech_range.last_transcript_start):
            return index
    raise HansardUnattributedSpeechError(f"Report {speech_range.report_id}: no row starts with {speech_range.last_transcript_start!r}")


def _is_unattributable(speech: ParsedSpeech, speaker: Optional[str]) -> bool:
    return speech.speaker == speaker and (speech.kind == SpeechKind.SPEECH or speech.kind == SpeechKind.UNCLASSIFIED)


def apply_unattributed_speech_range(speeches: list[ParsedSpeech], speech_range: UnattributedSpeechRange) -> list[ParsedSpeech]:
    start = _get_unattributed_range_start(speeches, speech_range)
    end = _get_unattributed_range_end(speeches, speech_range, start)
    return [
        ParsedSpeech(speaker=None, transcript=speech.transcript, kind=SpeechKind.SPEECH)
        if start <= index <= end and _is_unattributable(speech, speech_range.speaker) else speech
        for index, speech in enumerate(speeches)
    ]
