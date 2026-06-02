"""
One-off script: find Speech rows whose speaker is a paren-only annotation
(e.g. "(Accidents and violations)") or an italic sub-section divider
(e.g. "_HDB Policy Changes_"), delete all speeches for those reports,
and re-parse them with the fixed services/speech.py logic.
"""
import re
import sys

sys.path.insert(0, ".")

from sqlmodel import Session, create_engine, select

from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from database.speech import Speech
from services.speech import get_speeches, get_start_of_speech_line
from settings import settings

_ANNOTATION_RE = re.compile(r"^\(.*\)$|^_[^_].*_$")
_HONORIFIC_RE = re.compile(r"\b(Mr|Mrs|Ms|Dr|Prof|Mdm|Assoc|Inche|Tuan|Haji|The|Er)\b")


def _is_annotation_speaker(name: str) -> bool:
    return bool(_ANNOTATION_RE.match(name)) and not _HONORIFIC_RE.search(name)


def main():
    engine = create_engine(url=settings.database_url)
    with Session(engine) as session:
        all_speeches = session.exec(select(Speech)).all()
        bad_report_ids = {
            sp.report_id for sp in all_speeches
            if sp.speaker and _is_annotation_speaker(sp.speaker)
        }
        print(f"Reports with annotation speaker names: {len(bad_report_ids)}")

        crud = CRUDSpeech(session)
        report_crud = CRUDReport(session)
        deleted_total = 0
        inserted_total = 0

        reports_by_id = {r.id: r for r in report_crud.get_by_ids(list(bad_report_ids))}

        for report_id in sorted(bad_report_ids):
            db_report = reports_by_id.get(report_id)
            if db_report is None:
                print(f"  report {report_id}: not found, skipping")
                continue

            deleted = crud.delete_by_report_id(report_id)
            deleted_total += deleted

            if db_report.markdown_content is None:
                print(f"  report {report_id}: no markdown, skipped re-parse")
                continue

            start_line = get_start_of_speech_line(
                db_report.markdown_content,
                db_report.title,
                db_report.subtitle,
                db_report.original_title,
                db_report.report_type,
            )
            if start_line is None:
                print(f"  report {report_id}: could not find start line, skipped re-parse")
                continue

            new_speeches = [
                Speech(
                    ordinal=ordinal + 1,
                    speaker=speech.speaker,
                    transcript=speech.transcript,
                    report_id=report_id,
                )
                for ordinal, speech in enumerate(
                    get_speeches(db_report.markdown_content, start_line, db_report.report_type)
                )
            ]
            crud.create_many(new_speeches)
            inserted_total += len(new_speeches)

        print(f"\nDone. Deleted {deleted_total} rows, inserted {inserted_total} rows across {len(bad_report_ids)} reports.")


if __name__ == "__main__":
    main()
