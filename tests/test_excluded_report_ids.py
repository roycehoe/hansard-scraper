import json
from pathlib import Path

from schemas.excluded_report_id import ExcludedReportId

_DATA_FILE = Path(__file__).parent.parent / "data" / "excluded_report_ids.json"


def test_every_excluded_report_points_at_a_kept_report_that_is_not_excluded() -> None:
    entries = [ExcludedReportId.model_validate(entry) for entry in json.loads(_DATA_FILE.read_text())]

    excluded_report_ids = {entry.report_id for entry in entries}
    assert len(excluded_report_ids) == len(entries)
    assert not excluded_report_ids & {entry.kept_report_id for entry in entries}
