from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.attribution_text_share as attribution_text_share
from database.report import Report
from database.speaker import Speaker
from database.speech import Speech
from enums import ReportType, ReportVersion
from populate.attribution_figures import get_attribution_figures
from services.attribution import LINKED_CATEGORY
from tests.attribution_seed import seed_attribution_rows

_EXPECTED_FIGURES_FILE = Path(__file__).parent / "fixtures" / "attribution" / "figures.txt"
_NEW_PARLIAMENT = 15
_NEW_PARLIAMENT_GROUP = "Parliament 15"
_PREVIOUS_PARLIAMENT_GROUP = "Parliament 14"
_NEW_PARLIAMENT_SITTING_DATE = datetime(2025, 9, 5)
_NEW_PARLIAMENT_REPORT_COUNT = 1
_NEW_PARLIAMENT_LINKED_ROW_COUNT = 1
_SPEECH_NUMBER = 1


def test_script_output_is_unchanged(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seed_attribution_rows(scratch_session)
    monkeypatch.setattr(attribution_text_share, "engine", scratch_engine)
    output_path = tmp_path / "figures.txt"
    attribution_text_share.main(output_path)
    assert output_path.read_text(encoding="utf-8") == _EXPECTED_FIGURES_FILE.read_text(encoding="utf-8")


def test_parliament_15_has_its_own_group(scratch_session: Session) -> None:
    seed_attribution_rows(scratch_session)
    speaker = Speaker(name="Tan Ah Kow", party="PAP", is_legislative_assembly=False, parliament_number=_NEW_PARLIAMENT)
    report = Report(
        volumeNo=_NEW_PARLIAMENT,
        parlNo=_NEW_PARLIAMENT,
        sittingNo=None,
        sittingDate=_NEW_PARLIAMENT_SITTING_DATE,
        sno=_SPEECH_NUMBER,
        original_title="Rental Housing",
        title="Rental Housing",
        reportId="parliament-15-oral-answer",
        reportType=ReportType.ORAL_ANSWER,
        content="<p>Stored text</p>",
        markdown_content="**Mr Tan Ah Kow:** asked about rental flats.\n\n**Mr Lim Boon Heng:** More will be built.\n",
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )
    scratch_session.add_all([speaker, report])
    scratch_session.flush()
    scratch_session.add_all([
        Speech(ordinal=1, speaker="Mr Tan Ah Kow", transcript="asked about rental flats.", sitting_date=report.sitting_date, report_id=report.id, speaker_id=speaker.id),
        Speech(ordinal=2, speaker="Mr Lim Boon Heng", transcript="More will be built.", sitting_date=report.sitting_date, report_id=report.id),
    ])
    scratch_session.commit()

    group_figures_list = get_attribution_figures(scratch_session).groups

    groups = [group_figures.group for group_figures in group_figures_list]
    new_parliament_figures = group_figures_list[groups.index(_NEW_PARLIAMENT_GROUP)]
    assert groups.index(_NEW_PARLIAMENT_GROUP) == groups.index(_PREVIOUS_PARLIAMENT_GROUP) + 1
    assert new_parliament_figures.report_count == _NEW_PARLIAMENT_REPORT_COUNT
    assert new_parliament_figures.category_to_row_count[LINKED_CATEGORY] == _NEW_PARLIAMENT_LINKED_ROW_COUNT
