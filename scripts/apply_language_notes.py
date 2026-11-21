import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlmodel import Session

import database.speaker  # noqa: F401 registers Speaker so the speech.speaker_id foreign key resolves
from crud.report import CRUDReport
from crud.speech import CRUDSpeech, SpeechParseRow
from database.init import engine
from database.report import Report
from database.speech import Speech
from exceptions import HansardWriteCheckError
from logs import logger
from populate.written_tables import vacuum_analyze_written_tables
from schemas.unlabelled_speech import UnlabelledSpeechRange
from services.speech import get_parsed_speeches
from settings import settings
from utils.data_files import get_unlabelled_speech_ranges
from utils.markdown_parser import get_cleaned_report_markdown
from utils.speech_language_note import SpeechLanguageNoteChange
from utils.write_target import validate_can_write

# NOTE: wider than the parser's note pattern, because tags and &nbsp; sit between the words in report.content.
_LANGUAGE_NOTE_CONTENT_PATTERN = r"(?i)\((\s|&nbsp;|&#160;|<[^>]*>|[_*])*(in|dalam)(\s|&nbsp;|&#160;|<[^>]*>)+(mandar|malay|english|tamil|hokkien|cantonese|teochew|hakka)"
_REPORT_BATCH = 200


@dataclass(frozen=True)
class UnpairedLanguageNote:
    report_id: int
    ordinal: int
    language_note: str


@dataclass
class LanguageNotePlan:
    report_count: int
    language_note_changes: list[SpeechLanguageNoteChange] = field(default_factory=list)
    report_id_to_language_notes: dict[int, set[str]] = field(default_factory=dict)
    paired_note_count: int = 0
    unpaired_notes: list[UnpairedLanguageNote] = field(default_factory=list)
    unparsed_report_ids: list[int] = field(default_factory=list)


def _add_report(
    plan: LanguageNotePlan,
    report: Report,
    speech_rows: list[SpeechParseRow],
    report_id_to_unlabelled_range: dict[int, UnlabelledSpeechRange],
) -> None:
    if report.content is None:
        plan.unparsed_report_ids.append(report.id)
        return
    parsed_speeches = get_parsed_speeches(
        report,
        get_cleaned_report_markdown(report.content, report.report_version),
        report_id_to_unlabelled_range.get(report.id),
    )
    if parsed_speeches is None:
        plan.unparsed_report_ids.append(report.id)
        return
    key_to_speech_row = {
        (speech_row.ordinal, speech_row.speaker, speech_row.transcript): speech_row
        for speech_row in speech_rows
    }
    language_note_changes = []
    for ordinal, parsed_speech in enumerate(parsed_speeches, start=1):
        speech_row = key_to_speech_row.get(
            (ordinal, parsed_speech.speaker, parsed_speech.transcript)
        )
        if speech_row is None:
            if parsed_speech.language_note is not None:
                plan.unpaired_notes.append(
                    UnpairedLanguageNote(
                        report.id, ordinal, parsed_speech.language_note
                    )
                )
            continue
        if parsed_speech.language_note is not None:
            plan.paired_note_count += 1
        if speech_row.language_note != parsed_speech.language_note:
            language_note_changes.append(
                SpeechLanguageNoteChange(
                    speech_row.id,
                    speech_row.ordinal,
                    speech_row.speaker,
                    speech_row.transcript,
                    parsed_speech.language_note,
                )
            )
    if language_note_changes:
        plan.language_note_changes.extend(language_note_changes)
        plan.report_id_to_language_notes[report.id] = {
            language_note_change.language_note
            for language_note_change in language_note_changes
            if language_note_change.language_note is not None
        }


def _get_language_note_plan(
    session: Session, report_ids: list[int]
) -> LanguageNotePlan:
    report_id_to_unlabelled_range = {
        speech_range.report_id: speech_range
        for speech_range in get_unlabelled_speech_ranges()
    }
    plan = LanguageNotePlan(len(report_ids))
    for start in range(0, len(report_ids), _REPORT_BATCH):
        batch_report_ids = report_ids[start : start + _REPORT_BATCH]
        report_id_to_speech_rows = defaultdict(list)
        for speech_row in CRUDSpeech(session).get_parse_rows_by_report_ids(
            batch_report_ids
        ):
            report_id_to_speech_rows[speech_row.report_id].append(speech_row)
        for report in CRUDReport(session).get_by_ids(batch_report_ids):
            _add_report(
                plan,
                report,
                report_id_to_speech_rows[report.id],
                report_id_to_unlabelled_range,
            )
        session.expunge_all()
        logger.info(
            f"Read {min(start + _REPORT_BATCH, len(report_ids)):,}/{len(report_ids):,} reports, {len(plan.language_note_changes):,} rows to write"
        )
    return plan


def _log_plan(plan: LanguageNotePlan) -> None:
    language_note_to_row_count = Counter(
        language_note_change.language_note
        for language_note_change in plan.language_note_changes
        if language_note_change.language_note is not None
    )
    language_note_to_report_count = Counter(
        language_note
        for language_notes in plan.report_id_to_language_notes.values()
        for language_note in language_notes
    )
    cleared_count = len(plan.language_note_changes) - language_note_to_row_count.total()
    logger.info(
        f"Plan: {language_note_to_row_count.total():,} rows take a language note and {cleared_count:,} lose one, in {len(plan.report_id_to_language_notes):,} reports."
        f" Rows and reports by note: {', '.join(f'{language_note!r} {row_count:,} in {language_note_to_report_count[language_note]:,}' for language_note, row_count in language_note_to_row_count.most_common()) or 'none'}."
        f" Read {plan.report_count:,} reports. Notes in the parse: {plan.paired_note_count:,} paired with a stored row, {len(plan.unpaired_notes):,} not paired."
        f" Not read: {len(plan.unparsed_report_ids):,} reports with no text or no start of speech ({', '.join(map(str, plan.unparsed_report_ids)) or 'none'})"
    )
    for unpaired_note in plan.unpaired_notes:
        logger.info(
            f"Not paired: report {unpaired_note.report_id} ordinal {unpaired_note.ordinal} {unpaired_note.language_note!r}"
        )


def _validate_can_commit_language_notes(
    session: Session, report_ids: list[int]
) -> None:
    if _get_language_note_plan(session, report_ids).language_note_changes:
        raise HansardWriteCheckError(
            "Rows whose language note differs remain after the update"
        )


def apply_language_notes(report_ids: list[int], is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        planned_report_ids = report_ids or CRUDReport(session).get_ids_by_content_regex(
            _LANGUAGE_NOTE_CONTENT_PATTERN
        )
        plan = _get_language_note_plan(session, planned_report_ids)
        _log_plan(plan)
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        written_count = CRUDSpeech(
            session
        ).set_language_notes_bulk_by_ordinal_and_speaker_and_transcript(
            plan.language_note_changes
        )
        if written_count != len(plan.language_note_changes):
            raise HansardWriteCheckError(
                f"Rows changed since the plan was made: planned {len(plan.language_note_changes):,}, written {written_count:,}"
            )
        _validate_can_commit_language_notes(
            session, list(plan.report_id_to_language_notes)
        )
        session.commit()
        logger.info(f"Committed: {written_count:,} language notes")
        vacuum_analyze_written_tables(session, [Speech.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Set speech.language_note on stored rows from a fresh parse of report.content, on rows whose ordinal, label and transcript equal the parse"
    )
    parser.add_argument(
        "--report-id",
        type=int,
        nargs="+",
        action="extend",
        default=[],
        help="only these reports; without it every report whose text holds a language note",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write, then check the written reports equal the parse; without it the script only reports the plan",
    )
    arguments = parser.parse_args()
    apply_language_notes(arguments.report_id, arguments.commit)
