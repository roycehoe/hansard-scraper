import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Union

from schemas.hansard_report_response import (
    HansardReportNewResponse,
    HansardReportOldResponse,
)

RECHECK_WINDOW_DAYS = 14
UNLINKED_HALT_SHARE = 0.05
SINGAPORE_TIMEZONE = timezone(timedelta(hours=8))
_MAX_ALERT_LABELS = 20
_MAX_TELEGRAM_MESSAGE_LENGTH = 4_000
_PERCENT = 100
_FIRST_ALERT_WINDOW_DAYS = 1
_SINGULAR_COUNT = 1


def get_singapore_today(now: datetime) -> date:
    return now.astimezone(SINGAPORE_TIMEZONE).date()


def get_recheck_start_date(today: date) -> date:
    return today - timedelta(days=RECHECK_WINDOW_DAYS)


def get_probe_start_date(latest_stored_sitting_date: date, today: date) -> date:
    return min(latest_stored_sitting_date + timedelta(days=1), get_recheck_start_date(today))


def get_dates_between(first_date: date, last_date: date) -> list[date]:
    return [first_date + timedelta(days=day_offset) for day_offset in range((last_date - first_date).days + 1)]


def is_published_sitting_response(hansard_report_response: Union[HansardReportOldResponse, HansardReportNewResponse]) -> bool:
    if hansard_report_response.error_code is not None:
        return False
    if isinstance(hansard_report_response, HansardReportNewResponse):
        if hansard_report_response.metadata is not None and hansard_report_response.metadata.sitting_no is not None:
            return True
        if hansard_report_response.attendance_list is None:
            return False
        return len(hansard_report_response.attendance_list) > 0
    if hansard_report_response.sitting_no is not None:
        return True
    return hansard_report_response.html_full_content is not None


def is_held_report_alert_due(sitting_date: date, today: date) -> bool:
    recheck_start_date = get_recheck_start_date(today)
    return recheck_start_date <= sitting_date and sitting_date <= recheck_start_date + timedelta(days=_FIRST_ALERT_WINDOW_DAYS)


def get_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def get_unlinked_share(linked_row_count: int, named_unlinked_row_count: int) -> Optional[float]:
    named_row_count = linked_row_count + named_unlinked_row_count
    if named_row_count == 0:
        return None
    return named_unlinked_row_count / named_row_count


def is_unlinked_share_over_limit(unlinked_share: float) -> bool:
    return unlinked_share > UNLINKED_HALT_SHARE


def get_unexpected_parliament_numbers(
    parliament_numbers: set[int],
    stored_max_parliament_number: Optional[int],
    allowed_parliament_number: Optional[int],
) -> list[int]:
    return sorted(
        parliament_number
        for parliament_number in parliament_numbers
        if (stored_max_parliament_number is None or parliament_number > stored_max_parliament_number)
        and parliament_number != allowed_parliament_number
    )


def build_halt_message(reason: str) -> str:
    return f"Hansard refresh halted. {reason}"


def build_failure_message(reason: str) -> str:
    return f"Hansard refresh failed. {reason}"


def build_new_parliament_reason(parliament_numbers: list[int]) -> str:
    parliament_numbers_text = ", ".join(str(parliament_number) for parliament_number in parliament_numbers)
    return (
        f"New Parliament number {parliament_numbers_text} in the fetched responses. "
        "Load its members, then run refresh.py --allow-parliament N."
    )


def build_field_mapping_reason(field_losses: list[str]) -> str:
    return f"{len(field_losses)} fields failed the field mapping check. First: {field_losses[0].strip()}"


def _get_label_list_text(label_to_row_count: dict[str, int]) -> str:
    labels = sorted(label_to_row_count, key=lambda label: (-label_to_row_count[label], label))
    label_list_text = "; ".join(f"{label} ({label_to_row_count[label]} rows)" for label in labels[:_MAX_ALERT_LABELS])
    if len(labels) > _MAX_ALERT_LABELS:
        return f"{label_list_text} and {len(labels) - _MAX_ALERT_LABELS} more"
    return label_list_text


def build_unlinked_reason(unlinked_share: float, label_to_row_count: dict[str, int]) -> str:
    return (
        f"{unlinked_share * _PERCENT:.1f}% of new speech rows have a speaker label with no registry link, "
        f"above the {UNLINKED_HALT_SHARE * _PERCENT:.0f}% limit. Labels: {_get_label_list_text(label_to_row_count)}."
    )


def _get_count_text(count: int, noun: str) -> str:
    if count == _SINGULAR_COUNT:
        return f"{count:,} {noun}"
    return f"{count:,} {noun}s"


def build_summary_message(sittings_added: int, reports_added: int, speeches_added: int, linked_share: Optional[float]) -> str:
    message_parts = [
        _get_count_text(sittings_added, "sitting"),
        _get_count_text(reports_added, "report"),
        _get_count_text(speeches_added, "row"),
    ]
    if linked_share is not None:
        message_parts.append(f"{linked_share * _PERCENT:.1f}% linked")
    return ", ".join(message_parts)


def build_changed_report_message(report_id: str, sitting_date: str) -> str:
    return f"Report {report_id} of {sitting_date} changed on SPRS since it was stored. The stored text was kept."


def build_unlinked_labels_message(label_to_row_count: dict[str, int]) -> str:
    return (
        f"Speaker labels with no registry match: {_get_label_list_text(label_to_row_count)}. "
        "Add the members to the registry, then link them with scripts/apply_speaker_links.py."
    )


def build_held_report_message(report_id: str, sitting_date: str) -> str:
    return f"Report {report_id} of {sitting_date} still has no text after {RECHECK_WINDOW_DAYS} days and will not be fetched again."


def get_telegram_text(text: str) -> str:
    return text[:_MAX_TELEGRAM_MESSAGE_LENGTH]
