"""
Regression guard for stage 8 speech links in Parliaments 0 to 11.

Re-runs the stage 8 speech resolver once per distinct key and compares the result
with every stored speech.speaker_id. A key is (speaker string, parliament, sitting
date when the string starts with a date-dependent role, else None), the same memo
key as resolve_speech_rows. Read-only: nothing is written.

Imports the underscore-private _resolve_speech_speaker_id and _DATE_DEPENDENT_ROLES
from populate/speaker_links.py on purpose: the guard must run the exact resolver,
not a copy that can drift.

"The Chairman", a carried role, a bare head-of-state string and a bare "Mr Deputy Speaker"
can be linked by the two report-context passes, which a per-key call does not reproduce.
When the resolver returns None for such a key it is counted as context-linked, not
stale. When it returns an id, the id is compared as usual.

Run it before and after any change to populate/speaker_resolution_constants.py or
services/attendance.py. Exits 1 when any stored link is stale, else 0.

Usage:
    PYTHONPATH=. poetry run python scripts/trace_speaker_links.py
"""
import sys
from collections import Counter
from datetime import datetime
from typing import Optional

from sqlmodel import Session

from crud.report import CRUDReport
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech
from database.init import engine
from populate.speaker_links import (
    _DATE_DEPENDENT_ROLES,
    _REPORT_BATCH,
    _resolve_speech_speaker_id,
)
from populate.speaker_resolution_constants import HEAD_OF_STATE_TERMS
from services.attendance import build_speaker_lookups
from services.role_context import BARE_DEPUTY_RE, CARRIED_ROLES, CHAIRMAN_RE

_MAX_PARLIAMENT = 11

Key = tuple[str, int, Optional[datetime]]


def _is_context_linked(speaker: str) -> bool:
    return bool(
        CHAIRMAN_RE.match(speaker)
        or speaker in CARRIED_ROLES
        or speaker in HEAD_OF_STATE_TERMS
        or BARE_DEPUTY_RE.match(speaker.strip())
    )


def main() -> None:
    with Session(engine) as session:
        speakers = CRUDSpeaker(session).get_all()
        # Keep only (id, parliament, date): each Report carries its markdown.
        reports = [
            (report.id, report.parliament_number, report.sitting_date)
            for report in CRUDReport(session).get_all()
            if report.parliament_number is not None and report.parliament_number <= _MAX_PARLIAMENT
        ]
        name_and_parliament_to_speaker_id = {
            (speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None
        }
        speaker_id_to_name = {speaker.id: speaker.name for speaker in speakers}
        lookups = build_speaker_lookups(speakers)

        key_to_speaker_id_counts: dict[Key, Counter] = {}
        crud_speech = CRUDSpeech(session)
        for start in range(0, len(reports), _REPORT_BATCH):
            batch = reports[start : start + _REPORT_BATCH]
            report_id_to_parliament_and_date = {report_id: (parliament_number, sitting_date) for report_id, parliament_number, sitting_date in batch}
            for row in crud_speech.get_rows_by_report_ids(list(report_id_to_parliament_and_date)):
                if not row.speaker or row.speaker_id is None:
                    continue
                parliament_number, sitting_date = report_id_to_parliament_and_date[row.report_id]
                date_key = sitting_date if row.speaker.startswith(_DATE_DEPENDENT_ROLES) else None
                key_to_speaker_id_counts.setdefault((row.speaker, parliament_number, date_key), Counter())[row.speaker_id] += 1

    total_rows = sum(sum(counter.values()) for counter in key_to_speaker_id_counts.values())
    agree, context, stale = [0, 0], [0, 0], []
    for (speaker, parliament_number, sitting_date), counts in key_to_speaker_id_counts.items():
        key_row_count = sum(counts.values())
        resolved = _resolve_speech_speaker_id(speaker, parliament_number, sitting_date, lookups, name_and_parliament_to_speaker_id)
        if resolved is None and _is_context_linked(speaker):
            context[0] += 1
            context[1] += key_row_count
        elif set(counts) == {resolved}:
            agree[0] += 1
            agree[1] += key_row_count
        else:
            bad_rows = sum(row_count for speaker_id, row_count in counts.items() if speaker_id != resolved)
            stale.append((bad_rows, speaker, parliament_number, sitting_date, counts, resolved))

    stale_rows = sum(stale_entry[0] for stale_entry in stale)
    print(f"Total: {len(key_to_speaker_id_counts)} keys, {total_rows} rows")
    print(f"Agree: {agree[0]} keys, {agree[1]} rows")
    print(f"Context-linked, not re-evaluated: {context[0]} keys, {context[1]} rows")
    print(f"Stale: {len(stale)} keys, {stale_rows} rows")
    for bad_rows, speaker, parliament_number, sitting_date, counts, resolved in sorted(
        stale, key=lambda stale_entry: (-stale_entry[0], stale_entry[1], stale_entry[2])
    ):
        stored_text = ", ".join(
            f"{speaker_id} {speaker_id_to_name.get(speaker_id)!r} x{row_count}" for speaker_id, row_count in sorted(counts.items())
        )
        print(
            f"{bad_rows:>6}  {speaker!r}  P{parliament_number}  {sitting_date.date() if sitting_date is not None else '-'}  "
            f"stored [{stored_text}]  resolved {resolved} {speaker_id_to_name.get(resolved)!r}"
        )
    sys.exit(1 if stale_rows else 0)


if __name__ == "__main__":
    main()
