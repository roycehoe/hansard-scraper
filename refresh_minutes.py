import argparse
from datetime import date, datetime, timezone

from sqlmodel import Session

from database.init import build_read_only_engine, engine
from exceptions import (
    HansardGatewayError,
    HansardMinutesIndexUnavailableError,
    HansardSettingError,
)
from gateway.telegram import send_telegram_message
from logs import logger
from populate.minutes import MinutesPlan, get_minutes_plan, populate_minutes
from services.refresh import (
    build_minutes_index_skipped_message,
    build_minutes_not_fetched_message,
    build_minutes_run_failure_message,
    build_minutes_to_review_message,
    get_alert_error_text,
    get_dates_between,
    get_recheck_start_date,
    get_singapore_today,
    get_telegram_text,
)
from settings import settings


def _send_alert(text: str) -> None:
    if settings.telegram_bot_token is None:
        return
    if settings.telegram_chat_id is None:
        return
    try:
        send_telegram_message(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            get_telegram_text(text),
        )
    except HansardGatewayError as error:
        logger.warning(f"Alert not sent: {error}")


def _get_dates_text(sitting_dates: list[date]) -> str:
    if not sitting_dates:
        return "none"
    return ", ".join(sitting_date.isoformat() for sitting_date in sitting_dates)


def _get_range_text(sitting_dates: list[date]) -> str:
    if not sitting_dates:
        return "none"
    return f"{sitting_dates[0].isoformat()} to {sitting_dates[-1].isoformat()}"


def _log_minutes_plan(minutes_plan: MinutesPlan) -> None:
    logger.info(
        f"Index page: {len(minutes_plan.listed_sitting_dates)} sittings listed, {_get_range_text(minutes_plan.listed_sitting_dates)}"
    )
    logger.info(
        f"New LISTED rows: {_get_dates_text([index_row.sitting_date for index_row in minutes_plan.new_index_rows])}"
    )
    logger.info(
        f"Rows moved to LISTED: {_get_dates_text([listing_move.index_row.sitting_date for listing_move in minutes_plan.listing_moves])}"
    )
    logger.info(
        f"New NOT_YET_LISTED rows: {_get_dates_text(minutes_plan.not_yet_listed_dates)}"
    )
    logger.info(f"Files to fetch: {_get_dates_text(minutes_plan.file_sitting_dates)}")


def _validate_can_store_minutes() -> None:
    if settings.telegram_bot_token is None:
        raise HansardSettingError("A commit run sends alerts and needs TELEGRAM_BOT_TOKEN")
    if settings.telegram_chat_id is None:
        raise HansardSettingError("A commit run sends alerts and needs TELEGRAM_CHAT_ID")


def refresh_minutes(now: datetime, is_commit: bool) -> None:
    today = get_singapore_today(now)
    recheck_window_dates = set(get_dates_between(get_recheck_start_date(today), today))
    if not is_commit:
        with Session(build_read_only_engine(settings.database_url)) as session:
            minutes_plan = get_minutes_plan(session, recheck_window_dates)
        _log_minutes_plan(minutes_plan)
        logger.info("Dry run: nothing written")
        return

    _validate_can_store_minutes()
    with Session(engine) as session:
        try:
            minutes_step_result = populate_minutes(session, recheck_window_dates)
        except HansardGatewayError as error:
            _send_alert(build_minutes_index_skipped_message(str(error)))
            return
        except HansardMinutesIndexUnavailableError as error:
            _send_alert(build_minutes_index_skipped_message(str(error)))
            return
        except Exception as unexpected_failure:  # noqa: BLE001 a failed run alerts before the error propagates
            _send_alert(
                build_minutes_run_failure_message(
                    get_alert_error_text(unexpected_failure)
                )
            )
            raise
    for minutes_to_review in minutes_step_result.minutes_to_review:
        _send_alert(
            build_minutes_to_review_message(
                minutes_to_review.sitting_date, minutes_to_review.status_note
            )
        )
    if minutes_step_result.minutes_not_fetched:
        _send_alert(
            build_minutes_not_fetched_message(
                {
                    minutes_not_fetched.sitting_date: minutes_not_fetched.reason
                    for minutes_not_fetched in minutes_step_result.minutes_not_fetched
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the minutes step of the daily refresh on its own: read the minutes index page and store the files of listed sittings"
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write the rows and files; without it the run only reads the index page and logs the plan",
    )
    arguments = parser.parse_args()
    refresh_minutes(datetime.now(timezone.utc), arguments.commit)
