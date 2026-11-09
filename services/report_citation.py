import re
from datetime import date
from typing import Optional

from crud.speech import SpeechCitationRow
from utils.printed_citation import PrintedCitation, ResumptionHeading

_QUOTE_MARKS = '"“”'
_ZERO_WIDTH_SPACE = "​"
_EMPHASIS_MARK = "_"
_EMPHASIS_PAIR_TOUCHING_QUOTE_RE = re.compile(
    rf"(?<=[{_QUOTE_MARKS}])_\s_|_\s_(?=[{_QUOTE_MARKS}])"
)
_WHITESPACE_RE = re.compile(r"\s+")
_QUOTE_RE = re.compile(rf"[{_QUOTE_MARKS}]")
_NOTE_RE = re.compile(r"\[\s*Please\s+refer\s+to(.*?)\]", re.IGNORECASE)
_OFFICIAL_REPORT_RE = re.compile(r"Official\s+Report", re.IGNORECASE)
_TAIL_RE = re.compile(
    r"Official\s+Report[,\s]+(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month>[A-Za-z]+)[,\s]+(?P<year>\d{4})"
    r"[,\s]+Vol(?:ume|\.)?\s*\d+[,\s]+(?:Issue|No\.?)\s*(?:No\.?\s*)?\d+",
    re.IGNORECASE,
)
_SECTION_RE = re.compile(
    rf"[,\s]+[A-Z][^.;{_QUOTE_MARKS}\[\]]*?\s+section", re.IGNORECASE
)
_TITLE_SEPARATOR_RE = re.compile(
    rf"[{_QUOTE_MARKS}]\s*[;,]?\s*(?:and\s+)?(?:\([a-z]\)\s*)?[{_QUOTE_MARKS}]",
    re.IGNORECASE,
)
_LEADING_JOINER_RE = re.compile(r"^[;,\s]*(?:and\s+)?(?:\([a-z]\)\s*)?", re.IGNORECASE)
_MAX_HEADING_GAP = 120
_HEADING_RE = re.compile(
    r"^\W*(?P<heading>(?:Order\s+read\s+for\s+)?(?:the\s+)?Resumption\s+of\s+Debate\s+on\s+"
    rf".{{0,{_MAX_HEADING_GAP}}}?[\[\(]\s*(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>[A-Za-z]+)[,.\s]+(?P<year>\d{{4}})\s*[\]\)])",
    re.IGNORECASE,
)
_MONTH_NAME_TO_NUMBER = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _remove_parser_marks(transcript: str) -> str:
    without_pairs = _EMPHASIS_PAIR_TOUCHING_QUOTE_RE.sub(
        "", transcript.replace(_ZERO_WIDTH_SPACE, "")
    )
    return _WHITESPACE_RE.sub(" ", without_pairs.replace(_EMPHASIS_MARK, "")).strip()


def _get_printed_date(day: str, month: str, year: str) -> Optional[date]:
    month_number = _MONTH_NAME_TO_NUMBER.get(month.lower())
    if month_number is None:
        return None
    try:
        return date(int(year), month_number, int(day))
    except ValueError:
        return None


def _get_printed_titles(title_text: str) -> list[str]:
    quote_positions = [
        quote_match.start() for quote_match in _QUOTE_RE.finditer(title_text)
    ]
    if not quote_positions:
        return []
    if len(quote_positions) == 1:
        # NOTE: one quote mark means the opening quote was not printed, so the title ends at the closing one
        return [_LEADING_JOINER_RE.sub("", title_text[: quote_positions[0]]).strip()]
    return [
        title.strip().rstrip(",").strip()
        for title in _TITLE_SEPARATOR_RE.split(
            title_text[quote_positions[0] + 1 : quote_positions[-1]]
        )
    ]


def _build_note_citations(
    note_text: str, speech_citation_row: SpeechCitationRow
) -> list[PrintedCitation]:
    printed_citations = []
    position = 0
    for tail_match in _TAIL_RE.finditer(note_text):
        section_match = _SECTION_RE.match(note_text, tail_match.end())
        tail_end = tail_match.end() if section_match is None else section_match.end()
        printed_citation = _LEADING_JOINER_RE.sub(
            "", note_text[position:tail_end]
        ).strip()
        titles = _get_printed_titles(note_text[position : tail_match.start()])
        printed_date = _get_printed_date(
            tail_match.group("day"), tail_match.group("month"), tail_match.group("year")
        )
        position = tail_end
        for title in titles or [""]:
            printed_citations.append(
                PrintedCitation(
                    report_id=speech_citation_row.report_id,
                    ordinal=speech_citation_row.ordinal,
                    printed_citation=printed_citation,
                    printed_title=title or None,
                    printed_date=printed_date,
                    paragraph=speech_citation_row.transcript,
                )
            )
    if _OFFICIAL_REPORT_RE.search(note_text, position) is not None:
        printed_citations.append(
            PrintedCitation(
                report_id=speech_citation_row.report_id,
                ordinal=speech_citation_row.ordinal,
                printed_citation=_LEADING_JOINER_RE.sub(
                    "", note_text[position:]
                ).strip(),
                printed_title=None,
                printed_date=None,
                paragraph=speech_citation_row.transcript,
            )
        )
    return printed_citations


def get_printed_citations(
    speech_citation_row: SpeechCitationRow,
) -> list[PrintedCitation]:
    transcript = _remove_parser_marks(speech_citation_row.transcript)
    return [
        printed_citation
        for note_match in _NOTE_RE.finditer(transcript)
        for printed_citation in _build_note_citations(
            note_match.group(1), speech_citation_row
        )
    ]


def get_resumption_heading(
    speech_citation_row: SpeechCitationRow,
) -> Optional[ResumptionHeading]:
    heading_match = _HEADING_RE.match(
        _remove_parser_marks(speech_citation_row.transcript)
    )
    if heading_match is None:
        return None
    return ResumptionHeading(
        report_id=speech_citation_row.report_id,
        ordinal=speech_citation_row.ordinal,
        printed_citation=heading_match.group("heading"),
        printed_date=_get_printed_date(
            heading_match.group("day"),
            heading_match.group("month"),
            heading_match.group("year"),
        ),
        paragraph=speech_citation_row.transcript,
    )
