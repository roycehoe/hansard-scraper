import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlmodel import Session, col, select

from database.bill import Bill, BillReport
from database.bill_key import BillKey
from database.report import Report
from database.speaker import Speaker
from database.speech import Speech
from enums import BillReportRole, ReportType, SpeechKind
from utils.title_key import get_title_key

_PARLIAMENT_NUMBER = 12


def seed_bill_report(
    session: Session,
    report_id: str,
    report_type: ReportType,
    sitting_date: datetime,
    title: str,
    lines: list[str],
) -> int:
    report = Report(
        volumeNo=1,
        parlNo=_PARLIAMENT_NUMBER,
        sittingNo=None,
        sittingDate=sitting_date,
        sno=1,
        original_title=title,
        title=title,
        reportId=report_id,
        reportType=report_type.value,
        content=None,
        markdown_content=None,
        htmlFileName=None,
        reportVersion="sprs3",
    )
    session.add(report)
    session.flush()
    assert report.id is not None
    session.add_all(
        Speech(
            ordinal=ordinal,
            speaker=None,
            transcript=line,
            sitting_date=sitting_date,
            report_type=report.report_type,
            report_id=report.id,
        )
        for ordinal, line in enumerate(lines, start=1)
    )
    session.commit()
    return report.id


def seed_speaker(session: Session, name: str) -> int:
    speaker = Speaker(
        name=name,
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=_PARLIAMENT_NUMBER,
    )
    session.add(speaker)
    session.commit()
    assert speaker.id is not None
    return speaker.id


def seed_bill(
    session: Session, title: str, report_id_to_role: dict[int, BillReportRole]
) -> int:
    sitting_dates = session.exec(
        select(Report.sitting_date).where(col(Report.id).in_(report_id_to_role))
    ).all()
    bill = Bill(
        title=title,
        title_key=get_title_key(title),
        first_sitting_date=min(sitting_dates),
        last_sitting_date=max(sitting_dates),
        is_passed=False,
    )
    session.add(bill)
    session.flush()
    assert bill.id is not None
    session.add_all(
        BillReport(role=role, bill_id=bill.id, report_id=report_id)
        for report_id, role in report_id_to_role.items()
    )
    session.commit()
    return bill.id


def seed_stored_bill(
    session: Session,
    title: str,
    report_ids: list[int],
    first_sitting_date: datetime,
    last_sitting_date: datetime,
    is_passed: bool,
    bill_key: Optional[str],
) -> int:
    bill = Bill(
        title=title,
        title_key=get_title_key(title),
        first_sitting_date=first_sitting_date,
        last_sitting_date=last_sitting_date,
        is_passed=is_passed,
    )
    session.add(bill)
    session.flush()
    assert bill.id is not None
    session.add_all(
        BillReport(role=BillReportRole.READING, bill_id=bill.id, report_id=report_id)
        for report_id in report_ids
    )
    if bill_key is not None:
        session.add(BillKey(act_count=0, bill_key=bill_key, bill_id=bill.id))
    session.commit()
    return bill.id


def seed_speech(
    session: Session,
    report_id: int,
    ordinal: int,
    speaker: Optional[str],
    speaker_id: Optional[int],
    kind: SpeechKind,
    transcript: str,
) -> None:
    report = session.get(Report, report_id)
    assert report is not None
    session.add(
        Speech(
            ordinal=ordinal,
            speaker=speaker,
            transcript=transcript,
            kind=kind,
            speaker_id=speaker_id,
            sitting_date=report.sitting_date,
            report_type=report.report_type,
            report_id=report_id,
        )
    )
    session.commit()


BILL_SPEECHES_FIRST_SPRS_REPORT_ID = "speeches-first"
BILL_SPEECHES_THIRD_SPRS_REPORT_ID = "speeches-third"
SPEAKER_A_LABEL = "Ms A"
SPEAKER_B_LABEL = "Mr B"


@dataclass(frozen=True)
class SeededBillSpeeches:
    bill_id: int
    first_report_id: int
    third_report_id: int
    speaker_a_id: int
    speaker_b_id: int


def seed_bill_speeches(session: Session) -> SeededBillSpeeches:
    speaker_a_id = seed_speaker(session, SPEAKER_A_LABEL)
    speaker_b_id = seed_speaker(session, SPEAKER_B_LABEL)
    first_report_id = seed_bill_report(
        session,
        BILL_SPEECHES_FIRST_SPRS_REPORT_ID,
        ReportType.BILL_INTRODUCTION,
        datetime(2024, 11, 12),
        "Food Bill",
        [],
    )
    third_report_id = seed_bill_report(
        session,
        BILL_SPEECHES_THIRD_SPRS_REPORT_ID,
        ReportType.BILL,
        datetime(2025, 1, 8),
        "Food Bill",
        [],
    )
    first_report_rows = (
        (1, None, None, SpeechKind.PROCEDURAL, "Bill read a First time."),
        (2, SPEAKER_A_LABEL, speaker_a_id, SpeechKind.SPEECH, "I support the Bill."),
        (3, SPEAKER_B_LABEL, speaker_b_id, SpeechKind.SPEECH, "I have a question."),
        (4, SPEAKER_A_LABEL, speaker_a_id, SpeechKind.SPEECH, "I thank the House."),
        (5, "Hon Member", None, SpeechKind.SPEECH, "Sir."),
    )
    third_report_rows = (
        (
            1,
            None,
            None,
            SpeechKind.UNCLASSIFIED,
            "Bill accordingly read a Second time and committed to a Committee of the whole House.",
        ),
        (2, SPEAKER_A_LABEL, speaker_a_id, SpeechKind.SPEECH, "Clause 1 is agreed."),
        (3, None, None, SpeechKind.PROCEDURAL, "Bill read a Third time and passed."),
        (
            4,
            SPEAKER_A_LABEL,
            speaker_a_id,
            SpeechKind.SPEECH,
            "Bill read a Third time and passed.",
        ),
    )
    for ordinal, speaker, speaker_id, kind, transcript in first_report_rows:
        seed_speech(
            session, first_report_id, ordinal, speaker, speaker_id, kind, transcript
        )
    for ordinal, speaker, speaker_id, kind, transcript in third_report_rows:
        seed_speech(
            session, third_report_id, ordinal, speaker, speaker_id, kind, transcript
        )
    bill_id = seed_bill(
        session,
        "Food Bill",
        {
            first_report_id: BillReportRole.READING,
            third_report_id: BillReportRole.READING,
        },
    )
    return SeededBillSpeeches(
        bill_id, first_report_id, third_report_id, speaker_a_id, speaker_b_id
    )


_ESTATE_DUTY_ACT_TEXT = """\
LEGISLATIVE HISTORY
 1. Act 3 of 2025 — Estate Duty Act 2025
     Bill                             :   9/2024
     First Reading                    :   2 December 2024
     Second and Third Readings        :   15 January 2025
     Commencement                     :   1 March 2025
 2. 2025 Revised Edition — Estate Duty Act 2025
     Operation                        :   31 December 2025
Abbreviations
"""
_UNAMENDED_ACT_TEXT = "WATER ACT 2025\n\nPart 1\n"


def write_harvest(directory: Path) -> None:
    (directory / "acts.json").write_text(
        json.dumps(
            [
                {"sso_code": "EDA2025", "title": "Estate Duty Act 2025"},
                {"sso_code": "WA2025", "title": "Water Act 2025"},
                {"sso_code": "GONE1999", "title": "Gone Act 1999"},
            ]
        ),
        encoding="utf8",
    )
    (directory / "EDA2025.txt").write_text(_ESTATE_DUTY_ACT_TEXT, encoding="utf8")
    (directory / "WA2025.txt").write_text(_UNAMENDED_ACT_TEXT, encoding="utf8")
