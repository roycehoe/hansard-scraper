from datetime import date, datetime, timedelta, timezone

from schemas.hansard_report_response import (
    HansardReportNewResponse,
    HansardReportOldResponse,
)
from services.refresh import (
    RECHECK_WINDOW_DAYS,
    build_changed_report_message,
    build_failure_message,
    build_field_mapping_reason,
    build_halt_message,
    build_held_report_message,
    build_new_parliament_reason,
    build_summary_message,
    build_unlinked_labels_message,
    build_unlinked_reason,
    get_content_hash,
    get_dates_between,
    get_probe_start_date,
    get_recheck_start_date,
    get_singapore_today,
    get_sitting_date_key,
    get_telegram_text,
    get_unexpected_parliament_numbers,
    get_unlinked_share,
    is_held_report_alert_due,
    is_published_sitting_response,
    is_unlinked_share_over_limit,
)
from utils.sitting_dates import MonthWindow, get_month_windows

_TODAY = date(2025, 4, 20)
_RECENT_STORED_DAYS_AGO = 10
_OLD_STORED_DAYS_AGO = 30
_SITTING_DATE = date(2025, 4, 8)
_SITTING_DATE_KEY = "8-4-2025"
_ATTENDANCE_ENTRY = {"mpName": "Mr Speaker", "attendance": True}
_FIRST_DATE = date(2025, 4, 1)
_LAST_DATE = date(2025, 4, 3)
_CONTENT = "<p>The Minister replied.</p>"
_CHANGED_CONTENT = "<p>The Minister replies.</p>"
_STORED_MAX_PARLIAMENT_NUMBER = 14
_NEW_PARLIAMENT_NUMBER = 15
_LATER_PARLIAMENT_NUMBER = 16
_LINKED_ROW_COUNT = 95
_UNLINKED_ROW_COUNT_AT_LIMIT = 5
_SHARE_AT_LIMIT = 0.05
_SHARE_OVER_LIMIT = 0.0501
_SUMMARY = "2 sittings, 14 reports, 1,203 rows, 98.9% linked"
_SINGULAR_SUMMARY = "1 sitting, 1 report, 1 row, 100.0% linked"
_SUMMARY_COUNTS = (2, 14, 1203)
_SUMMARY_LINKED_SHARE = 0.989
_LABEL_CAP = 20
_LABEL_COUNT_OVER_CAP = 21
_UNLINKED_SHARE = 0.06
_UNLINKED_LABEL = "Mr Nobody"
_UNLINKED_LABEL_ROW_COUNT = 3
_REPORT_ID = "debate-1"
_MAX_TELEGRAM_LENGTH = 4_000
_FORBIDDEN_WORDS = ("—", "please")
_FIELD_LOSS = "  FAIL  raw['title']='x'  →  .title=None"


def test_singapore_today_is_the_local_calendar_date() -> None:
    assert get_singapore_today(datetime(2025, 4, 19, 20, 0, tzinfo=timezone.utc)) == date(2025, 4, 20)


def test_probe_starts_at_the_window_when_the_last_sitting_is_recent() -> None:
    latest_stored_sitting_date = _TODAY - timedelta(days=_RECENT_STORED_DAYS_AGO)

    assert get_probe_start_date(latest_stored_sitting_date, _TODAY) == _TODAY - timedelta(days=RECHECK_WINDOW_DAYS)


def test_probe_starts_after_the_last_sitting_when_it_is_old() -> None:
    latest_stored_sitting_date = _TODAY - timedelta(days=_OLD_STORED_DAYS_AGO)

    assert get_probe_start_date(latest_stored_sitting_date, _TODAY) == latest_stored_sitting_date + timedelta(days=1)


def test_recheck_starts_fourteen_days_back() -> None:
    assert get_recheck_start_date(_TODAY) == date(2025, 4, 6)


def test_dates_between_are_inclusive_and_ascending() -> None:
    assert get_dates_between(_FIRST_DATE, _LAST_DATE) == [date(2025, 4, 1), date(2025, 4, 2), date(2025, 4, 3)]


def test_month_windows_inside_one_month_is_one_window() -> None:
    assert get_month_windows(_FIRST_DATE, _LAST_DATE) == [MonthWindow(_FIRST_DATE, _LAST_DATE)]


def test_month_windows_split_at_each_month_end() -> None:
    assert get_month_windows(date(2025, 11, 20), date(2026, 1, 5)) == [
        MonthWindow(date(2025, 11, 20), date(2025, 11, 30)),
        MonthWindow(date(2025, 12, 1), date(2025, 12, 31)),
        MonthWindow(date(2026, 1, 1), date(2026, 1, 5)),
    ]


def test_month_windows_from_a_month_end_start_with_one_day() -> None:
    assert get_month_windows(date(2024, 8, 31), date(2024, 9, 12)) == [
        MonthWindow(date(2024, 8, 31), date(2024, 8, 31)),
        MonthWindow(date(2024, 9, 1), date(2024, 9, 12)),
    ]


def test_sitting_date_key_is_unpadded() -> None:
    assert get_sitting_date_key(_SITTING_DATE) == _SITTING_DATE_KEY


def test_published_sitting_responses() -> None:
    assert not is_published_sitting_response(HansardReportNewResponse.model_validate({"errorCode": "404", "metadata": {"sittingNO": 1}}))
    assert is_published_sitting_response(HansardReportNewResponse.model_validate({"metadata": {"sittingNO": 1}}))
    assert is_published_sitting_response(HansardReportNewResponse.model_validate({"metadata": {}, "attendanceList": [_ATTENDANCE_ENTRY]}))
    assert not is_published_sitting_response(HansardReportNewResponse.model_validate({"metadata": {}, "attendanceList": []}))
    assert is_published_sitting_response(HansardReportOldResponse.model_validate({"sittingNo": 1}))
    assert not is_published_sitting_response(HansardReportOldResponse.model_validate({}))


def test_held_report_alert_is_due_on_the_window_first_two_days_only() -> None:
    recheck_start_date = get_recheck_start_date(_TODAY)

    assert is_held_report_alert_due(recheck_start_date, _TODAY)
    assert is_held_report_alert_due(recheck_start_date + timedelta(days=1), _TODAY)
    assert not is_held_report_alert_due(recheck_start_date + timedelta(days=2), _TODAY)
    assert not is_held_report_alert_due(recheck_start_date - timedelta(days=1), _TODAY)


def test_content_hash_is_stable_and_changes_on_one_character() -> None:
    assert get_content_hash(_CONTENT) == get_content_hash(_CONTENT)
    assert get_content_hash(_CONTENT) != get_content_hash(_CHANGED_CONTENT)


def test_unlinked_share_is_none_with_no_named_rows() -> None:
    assert get_unlinked_share(0, 0) is None
    assert get_unlinked_share(_LINKED_ROW_COUNT, _UNLINKED_ROW_COUNT_AT_LIMIT) == _SHARE_AT_LIMIT


def test_unlinked_share_halts_only_above_five_percent() -> None:
    assert not is_unlinked_share_over_limit(_SHARE_AT_LIMIT)
    assert is_unlinked_share_over_limit(_SHARE_OVER_LIMIT)


def test_unexpected_parliament_numbers() -> None:
    parliament_numbers = {_STORED_MAX_PARLIAMENT_NUMBER, _NEW_PARLIAMENT_NUMBER, _LATER_PARLIAMENT_NUMBER}

    assert get_unexpected_parliament_numbers(parliament_numbers, _STORED_MAX_PARLIAMENT_NUMBER, None) == [
        _NEW_PARLIAMENT_NUMBER,
        _LATER_PARLIAMENT_NUMBER,
    ]
    assert get_unexpected_parliament_numbers(parliament_numbers, _STORED_MAX_PARLIAMENT_NUMBER, _NEW_PARLIAMENT_NUMBER) == [
        _LATER_PARLIAMENT_NUMBER,
    ]
    assert get_unexpected_parliament_numbers(parliament_numbers, None, None) == [
        _STORED_MAX_PARLIAMENT_NUMBER,
        _NEW_PARLIAMENT_NUMBER,
        _LATER_PARLIAMENT_NUMBER,
    ]


def test_summary_message() -> None:
    assert build_summary_message(*_SUMMARY_COUNTS, _SUMMARY_LINKED_SHARE) == _SUMMARY
    assert build_summary_message(1, 1, 1, 1.0) == _SINGULAR_SUMMARY


def test_summary_message_omits_the_share_when_unknown() -> None:
    assert build_summary_message(1, 0, 0, None) == "1 sitting, 0 reports, 0 rows"


def test_labels_message_caps_the_label_list() -> None:
    label_to_row_count = {f"Mr Member {i:02d}": 1 for i in range(_LABEL_COUNT_OVER_CAP)}

    message = build_unlinked_labels_message(label_to_row_count)

    assert message.count(" rows)") == _LABEL_CAP
    assert "and 1 more" in message
    assert "Mr Member 20" not in message


def test_labels_sort_by_row_count_then_label() -> None:
    message = build_unlinked_labels_message({"Mr B": 1, "Mr A": 1, "Mr C": 2})

    assert "Mr C (2 rows); Mr A (1 rows); Mr B (1 rows)" in message


def test_unlinked_reason_names_the_share_and_labels() -> None:
    reason = build_unlinked_reason(_UNLINKED_SHARE, {_UNLINKED_LABEL: _UNLINKED_LABEL_ROW_COUNT})

    assert "6.0%" in reason
    assert "Mr Nobody (3 rows)" in reason


def test_new_parliament_reason_names_the_numbers() -> None:
    assert "New Parliament number 15, 16" in build_new_parliament_reason([_NEW_PARLIAMENT_NUMBER, _LATER_PARLIAMENT_NUMBER])


def test_field_mapping_reason_names_the_first_loss() -> None:
    assert build_field_mapping_reason([_FIELD_LOSS, _FIELD_LOSS]).startswith("2 fields failed the field mapping check. First: FAIL")


def test_telegram_text_is_cut_to_the_cap() -> None:
    assert len(get_telegram_text("x" * (_MAX_TELEGRAM_LENGTH + 1))) == _MAX_TELEGRAM_LENGTH


def test_no_message_carries_an_em_dash_or_please() -> None:
    messages = (
        build_halt_message("Reason."),
        build_failure_message("Reason."),
        build_new_parliament_reason([_NEW_PARLIAMENT_NUMBER]),
        build_field_mapping_reason([_FIELD_LOSS]),
        build_unlinked_reason(_UNLINKED_SHARE, {_UNLINKED_LABEL: _UNLINKED_LABEL_ROW_COUNT}),
        build_summary_message(*_SUMMARY_COUNTS, _SUMMARY_LINKED_SHARE),
        build_changed_report_message(_REPORT_ID, _SITTING_DATE_KEY),
        build_unlinked_labels_message({_UNLINKED_LABEL: _UNLINKED_LABEL_ROW_COUNT}),
        build_held_report_message(_REPORT_ID, _SITTING_DATE_KEY),
    )

    for message in messages:
        for forbidden_word in _FORBIDDEN_WORDS:
            assert forbidden_word not in message.lower()
