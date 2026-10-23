from utils.data_files import get_excluded_report_ids


def test_every_excluded_report_points_at_a_kept_report_that_is_not_excluded() -> None:
    entries = get_excluded_report_ids()

    excluded_report_ids = {entry.report_id for entry in entries}
    assert len(excluded_report_ids) == len(entries)
    assert not excluded_report_ids & {entry.kept_report_id for entry in entries}
