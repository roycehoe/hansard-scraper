import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from sqlmodel import Session

import database.speech  # noqa: F401 registers Speech so the Report relationship resolves
from crud.report import CRUDReport
from crud.sitting import CRUDSitting
from crud.speech import CRUDSpeech
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from settings import settings
from utils.markdown_parser import REPAIRABLE_TEXT_PATTERN, repair_source_characters
from utils.text import TextChange
from utils.write_target import validate_can_write


@dataclass(frozen=True)
class SourceCharacterPlan:
    speech_transcripts: list[TextChange]
    speech_labels: list[TextChange]
    report_markdowns: list[TextChange]
    sitting_markdowns: list[TextChange]
    emptied_speech_ids: list[int]


def _repair_speech_text(text: str) -> str:
    return repair_source_characters(text).strip()


def _get_text_changes(text_changes: list[TextChange]) -> list[TextChange]:
    return [text_change for text_change in text_changes if text_change.after != text_change.before]


def _get_source_character_plan(session: Session) -> SourceCharacterPlan:
    speech_rows = CRUDSpeech(session).get_transcript_rows_by_transcript_regex(REPAIRABLE_TEXT_PATTERN)
    label_rows = CRUDSpeech(session).get_label_rows_by_speaker_regex(REPAIRABLE_TEXT_PATTERN)
    report_rows = CRUDReport(session).get_markdown_rows_by_markdown_content_regex(REPAIRABLE_TEXT_PATTERN)
    sitting_rows = CRUDSitting(session).get_markdown_rows_by_markdown_content_regex(REPAIRABLE_TEXT_PATTERN)
    transcript_changes = _get_text_changes([TextChange(row.id, row.transcript, _repair_speech_text(row.transcript)) for row in speech_rows])
    # NOTE: the parser drops a speech row with nothing left, which an update cannot do, so such a row stays as stored until the next parse write.
    return SourceCharacterPlan(
        [text_change for text_change in transcript_changes if text_change.after],
        _get_text_changes([TextChange(row.id, row.speaker, _repair_speech_text(row.speaker)) for row in label_rows]),
        _get_text_changes([TextChange(row.id, row.markdown_content, repair_source_characters(row.markdown_content)) for row in report_rows]),
        _get_text_changes([TextChange(row.id, row.markdown_content, repair_source_characters(row.markdown_content)) for row in sitting_rows]),
        [text_change.id for text_change in transcript_changes if not text_change.after],
    )


def _get_counts(source_character_plan: SourceCharacterPlan) -> dict[str, int]:
    return {
        "speech transcripts": len(source_character_plan.speech_transcripts),
        "speech labels": len(source_character_plan.speech_labels),
        "report markdowns": len(source_character_plan.report_markdowns),
        "sitting markdowns": len(source_character_plan.sitting_markdowns),
    }


def _write_source_characters(session: Session, source_character_plan: SourceCharacterPlan) -> None:
    written_counts = {
        "speech transcripts": CRUDSpeech(session).set_transcripts_bulk_by_transcript(source_character_plan.speech_transcripts),
        "speech labels": CRUDSpeech(session).set_speakers_bulk_by_speaker(source_character_plan.speech_labels),
        "report markdowns": CRUDReport(session).set_markdown_contents_bulk_by_markdown_content(source_character_plan.report_markdowns),
        "sitting markdowns": CRUDSitting(session).set_markdown_contents_bulk_by_markdown_content(source_character_plan.sitting_markdowns),
    }
    planned_counts = _get_counts(source_character_plan)
    if written_counts != planned_counts:
        raise HansardWriteCheckError(f"Rows changed since the plan was made: planned {planned_counts}, written {written_counts}")
    if any(_get_counts(_get_source_character_plan(session)).values()):
        raise HansardWriteCheckError("Text the source character repair rewrites remains after the update")


def apply_source_characters(is_commit: bool, plan_path: Optional[Path]) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        source_character_plan = _get_source_character_plan(session)
        for speech_id in source_character_plan.emptied_speech_ids:
            logger.warning(f"Speech {speech_id}: nothing left after the repair, left as stored")
        logger.info(f"Plan: {_get_counts(source_character_plan)}")
        if plan_path is not None:
            plan_path.write_text(json.dumps(asdict(source_character_plan), indent=1, ensure_ascii=False))
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        _write_source_characters(session, source_character_plan)
        session.commit()
        logger.info(f"Committed: {_get_counts(source_character_plan)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Repair the characters SPRS sends broken in stored speech, report and sitting text, as the parser now does")
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    parser.add_argument("--plan", type=Path, help="write the plan as JSON to this path")
    arguments = parser.parse_args()
    apply_source_characters(arguments.commit, arguments.plan)
