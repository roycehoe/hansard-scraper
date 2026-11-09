import re
from dataclasses import dataclass

from crud.speech import SpeechAskerRow
from enums import ReportPutToSource

_PUT_TO_OPENING_RE = re.compile(r"\b(?P<verb>[Aa]sk(?:ed)?)\s*the\s+")
_ASKED_VERB = "asked"
_OFFICE_HEADS = (
    "Prime Minister",
    "Deputy Prime Minister",
    "First Deputy Prime Minister",
    "Second Deputy Prime Minister",
    "Coordinating Minister",
    "Co-ordinating Minister",
    "Senior Minister",
    "Second Minister",
    "Acting Minister",
    "Acting Minister-in-charge",
    "Minister-in-charge",
    "Minister-in-Charge",
    "Minister in charge",
    "Minister of State",
    "Senior Minister of State",
    "Minister",
    "Chief Minister",
    "Chief Secretary",
    "Financial Secretary",
    "Attorney-General",
    "Leader of the House",
    "Minster",
    "Miniser",
    "Prirne Minister",
    "Depu ty Prime Minister",
)
_MISPRINTED_FOR_HEADS = ("Minister or", "Minister f or", "Minister, of")
_OFFICE_HEAD_RE = re.compile(
    r"\*?(?P<head>"
    + "|".join(
        sorted(
            [re.escape(head) for head in _OFFICE_HEADS]
            + [rf"{re.escape(head)}(?=\s+[A-Z])" for head in _MISPRINTED_FOR_HEADS],
            key=len,
            reverse=True,
        )
    )
    + r")(?![A-Za-z]|-[A-Za-z])"
)
_FOR_OR_OF_AFTER_HEAD_RE = re.compile(r"\s+(?:for|of)\s+(?:the\s+)?(?=[A-Z])")
_CAPITALISED_WORD_RE = re.compile(r"[A-Z][A-Za-z'’]*(?:-[A-Za-z]+)*")
_CAPITALISED_BRACKET_RE = re.compile(r"\s*\([A-Z][^()]*\)")
_TITLE_GAP_RE = re.compile(r"(?:\s*,|\s+and\b|\s+the\b)*\s*(?=[A-Z])")


@dataclass(frozen=True)
class PutToPhrase:
    office_printed: str
    printed_text: str
    source: ReportPutToSource
    first_ordinal: int


def _get_title_end(transcript: str, position: int) -> int:
    title_end = position
    while True:
        head_match = _OFFICE_HEAD_RE.match(transcript, position)
        if head_match is not None:
            position = title_end = head_match.end()
            for_or_of_match = _FOR_OR_OF_AFTER_HEAD_RE.match(transcript, position)
            if for_or_of_match is not None:
                position = for_or_of_match.end()
                continue
        else:
            word_match = _CAPITALISED_WORD_RE.match(transcript, position)
            if word_match is None:
                return title_end
            position = title_end = word_match.end()
        bracket_match = _CAPITALISED_BRACKET_RE.match(transcript, position)
        if bracket_match is not None:
            position = title_end = bracket_match.end()
        gap_match = _TITLE_GAP_RE.match(transcript, position)
        if gap_match is None:
            return title_end
        position = gap_match.end()


def get_put_to_phrases(
    speech_asker_rows: list[SpeechAskerRow], question_row_ordinals: frozenset[int]
) -> list[PutToPhrase]:
    office_printed_to_phrase: dict[str, PutToPhrase] = {}
    for speech_asker_row in speech_asker_rows:
        if speech_asker_row.ordinal not in question_row_ordinals:
            continue
        transcript = speech_asker_row.transcript
        opening_match = _PUT_TO_OPENING_RE.search(transcript)
        if opening_match is None:
            continue
        head_match = _OFFICE_HEAD_RE.match(transcript, opening_match.end())
        if head_match is None:
            continue
        title_end = _get_title_end(transcript, opening_match.end())
        office_printed = transcript[head_match.start("head") : title_end]
        if office_printed in office_printed_to_phrase:
            continue
        office_printed_to_phrase[office_printed] = PutToPhrase(
            office_printed,
            transcript[opening_match.start() : title_end],
            (
                ReportPutToSource.ASKED_THE
                if opening_match["verb"].lower() == _ASKED_VERB
                else ReportPutToSource.TO_ASK_THE
            ),
            speech_asker_row.ordinal,
        )
    return list(office_printed_to_phrase.values())
