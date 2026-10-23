import json
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import populate.attribution_figures
import scripts.attribution_text_share as attribution_text_share
from database.report import Report
from database.speaker import Speaker
from database.speech import Speech
from enums import ReportType, ReportVersion
from populate.attribution_figures import get_attribution_figures
from services.attribution import (
    HEADLINE_GROUP,
    LINKED_CATEGORY,
    build_attribution_figures_json,
)
from tests.attribution_seed import seed_attribution_rows

_EXPECTED_FIGURES_FILE = Path(__file__).parent / "fixtures" / "attribution" / "figures.txt"
_NEW_PARLIAMENT = 15
_NEW_PARLIAMENT_GROUP = "Parliament 15"
_PREVIOUS_PARLIAMENT_GROUP = "Parliament 14"
_NEW_PARLIAMENT_SITTING_DATE = datetime(2025, 9, 5)
_NEW_PARLIAMENT_REPORT_COUNT = 1
_NEW_PARLIAMENT_LINKED_ROW_COUNT = 1
_SPEECH_NUMBER = 1
_MEASURED_AT = datetime(2026, 10, 18, tzinfo=timezone.utc)
_MEASURED_AT_TEXT = "2026-10-18T00:00:00+00:00"
_HEADLINE_ZERO_ROW_REPORT_COUNT = 1
_STABLE_GROUP_KEYS = frozenset({
    "group",
    "report_count",
    "reports_with_rows_count",
    "zero_row_report_count",
    "linked_row_count",
    "named_unlinked_row_count",
    "adr_excluded_row_count",
    "no_speaker_row_count",
    "row_count",
    "linked_character_count",
    "body_character_count",
    "body_in_zero_row_reports",
})


def test_script_output_is_unchanged(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seed_attribution_rows(scratch_session)
    monkeypatch.setattr(attribution_text_share, "engine", scratch_engine)
    output_path = tmp_path / "figures.txt"
    attribution_text_share.attribution_text_share(output_path)
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
    assert report.id is not None
    scratch_session.add_all([
        Speech(ordinal=1, speaker="Mr Tan Ah Kow", transcript="asked about rental flats.", sitting_date=report.sitting_date, report_id=report.id, speaker_id=speaker.id),
        Speech(ordinal=2, speaker="Mr Lim Boon Heng", transcript="More will be built.", sitting_date=report.sitting_date, report_id=report.id),
    ])
    scratch_session.commit()

    all_group_figures = get_attribution_figures(scratch_session)

    group_names = [group_figures.group for group_figures in all_group_figures]
    new_parliament_figures = all_group_figures[group_names.index(_NEW_PARLIAMENT_GROUP)]
    assert group_names.index(_NEW_PARLIAMENT_GROUP) == group_names.index(_PREVIOUS_PARLIAMENT_GROUP) + 1
    assert new_parliament_figures.report_count == _NEW_PARLIAMENT_REPORT_COUNT
    assert new_parliament_figures.category_to_row_count[LINKED_CATEGORY] == _NEW_PARLIAMENT_LINKED_ROW_COUNT


def test_figures_json_carries_the_stable_fields(scratch_session: Session) -> None:
    seed_attribution_rows(scratch_session)

    figures_json = build_attribution_figures_json(get_attribution_figures(scratch_session), _MEASURED_AT)

    assert figures_json["measured_at"] == _MEASURED_AT_TEXT
    groups_json = cast(list[dict[str, object]], figures_json["groups"])
    for group_json in groups_json:
        assert _STABLE_GROUP_KEYS <= group_json.keys()
        assert group_json["zero_row_report_count"] == cast(int, group_json["report_count"]) - cast(int, group_json["reports_with_rows_count"])
        report_types_json = cast(list[dict[str, object]], group_json["report_types"])
        assert report_types_json != []
        assert all("collapse_report_count" in report_type_json for report_type_json in report_types_json)
    headline_json = next(group_json for group_json in groups_json if group_json["group"] == HEADLINE_GROUP)
    assert headline_json["zero_row_report_count"] == _HEADLINE_ZERO_ROW_REPORT_COUNT
    assert json.loads(json.dumps(figures_json)) == figures_json


def test_figures_do_not_depend_on_the_batch_size(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_attribution_rows(scratch_session)
    default_batch_figures_json = build_attribution_figures_json(get_attribution_figures(scratch_session), _MEASURED_AT)
    monkeypatch.setattr(populate.attribution_figures, "_REPORT_BATCH", 1)

    single_report_batch_figures_json = build_attribution_figures_json(get_attribution_figures(scratch_session), _MEASURED_AT)

    assert single_report_batch_figures_json == default_batch_figures_json
