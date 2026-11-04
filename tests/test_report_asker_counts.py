from database.report_asker import ReportAsker
from enums import ReportAskerSource
from populate.report_askers import ReportAskerCounts, _add_report


def _build_report_asker(
    source: ReportAskerSource, reader_printed_name: str | None
) -> ReportAsker:
    return ReportAsker(
        ordinal=1,
        printed_name="Mr Tay Beng Chuan",
        source=source,
        reader_printed_name=reader_printed_name,
        report_id=1,
        speaker_id=681,
        reader_speaker_id=None if reader_printed_name is None else 620,
    )


def test_rows_with_a_reader_count_every_source_and_stood_rows_without_one_are_counted_apart() -> (
    None
):
    counts = ReportAskerCounts()

    _add_report(
        counts,
        [
            _build_report_asker(ReportAskerSource.ASKED_LINE, "Mr Choo Wee Khiang"),
            _build_report_asker(ReportAskerSource.TO_ASK_LINE, "Mr Choo Wee Khiang"),
            _build_report_asker(
                ReportAskerSource.STOOD_IN_NAME_LINE, "Mr Choo Wee Khiang"
            ),
            _build_report_asker(ReportAskerSource.STOOD_IN_NAME_LINE, None),
            _build_report_asker(ReportAskerSource.ASKED_LINE, None),
        ],
    )

    assert (counts.rows_with_reader, counts.stood_rows_without_reader) == (3, 1)
