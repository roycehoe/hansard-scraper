from collections import Counter
from collections.abc import Iterator

import pytest

import scripts.attribution_text_share as attribution_text_share_script
from logs import logger
from services.attribution import (
    ADR_EXCLUDED_CATEGORY,
    HEADLINE_GROUP,
    LINKED_CATEGORY,
    NAMED_UNLINKED_CATEGORY,
    NO_SPEAKER_CATEGORY,
    GroupFigures,
)

_BREAKDOWN_HEADING = "Where the body text goes (chars, share of body):"
_BREAKDOWN_LABEL_WIDTH = 64
_BREAKDOWN_ROW_COUNT = 6
_EMPTY_BREAKDOWN_ROW_TAIL = " " * 11 + "0" + " " * 5 + "n/a"


@pytest.fixture
def logged_messages() -> Iterator[list[str]]:
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(message.record["message"]))
    yield messages
    logger.remove(sink_id)


def _get_group_figures(
    category_to_row_count: Counter[str],
    category_to_character_count: Counter[str],
    body_total: int,
) -> GroupFigures:
    return GroupFigures(
        group=HEADLINE_GROUP,
        report_count=0,
        reports_with_rows_count=0,
        category_to_row_count=category_to_row_count,
        category_to_character_count=category_to_character_count,
        body_total=body_total,
        body_in_zero_row_reports=0,
        report_type_to_figures={},
    )


def _log_figures(monkeypatch: pytest.MonkeyPatch, group_figures: GroupFigures) -> None:
    monkeypatch.setattr(
        attribution_text_share_script,
        "get_attribution_figures",
        lambda session: [group_figures],
    )
    attribution_text_share_script.attribution_text_share(None)


def _get_breakdown_row(label: str, character_count: int, percent: str) -> str:
    return f"  {label:<{_BREAKDOWN_LABEL_WIDTH}} {character_count:>12} {percent}"


def _get_breakdown_rows(messages: list[str]) -> list[str]:
    start = messages.index(_BREAKDOWN_HEADING) + 1
    return messages[start : start + _BREAKDOWN_ROW_COUNT]


def test_empty_table_logs_n_a_for_the_headline_lines(
    monkeypatch: pytest.MonkeyPatch, logged_messages: list[str]
) -> None:
    _log_figures(monkeypatch, _get_group_figures(Counter(), Counter(), 0))

    assert "1. ADR 0001 rate:  0 / 0 = n/a" in logged_messages
    assert "2. All-rows rate:  0 / 0 = n/a" in logged_messages
    assert "3. Text share:     0 / 0 chars = n/a" in logged_messages


def test_empty_table_logs_n_a_for_every_breakdown_row(
    monkeypatch: pytest.MonkeyPatch, logged_messages: list[str]
) -> None:
    _log_figures(monkeypatch, _get_group_figures(Counter(), Counter(), 0))

    breakdown_rows = _get_breakdown_rows(logged_messages)
    assert breakdown_rows[0].startswith("  linked rows")
    assert [row.endswith(_EMPTY_BREAKDOWN_ROW_TAIL) for row in breakdown_rows] == [True] * _BREAKDOWN_ROW_COUNT


def test_non_empty_table_logs_exact_headline_lines(
    monkeypatch: pytest.MonkeyPatch, logged_messages: list[str]
) -> None:
    category_to_row_count = Counter({LINKED_CATEGORY: 3, NAMED_UNLINKED_CATEGORY: 1, NO_SPEAKER_CATEGORY: 4})
    category_to_character_count = Counter({
        LINKED_CATEGORY: 3,
        NAMED_UNLINKED_CATEGORY: 2,
        ADR_EXCLUDED_CATEGORY: 0,
        NO_SPEAKER_CATEGORY: 4,
    })
    _log_figures(monkeypatch, _get_group_figures(category_to_row_count, category_to_character_count, 10))

    assert "1. ADR 0001 rate:  3 / 4 = 75.00%" in logged_messages
    assert "2. All-rows rate:  3 / 8 = 37.50%" in logged_messages
    assert "3. Text share:     3 / 10 chars = 30.00%" in logged_messages
    assert _get_breakdown_rows(logged_messages) == [
        _get_breakdown_row("linked rows", 3, " 30.00%"),
        _get_breakdown_row("named but unlinked rows", 2, " 20.00%"),
        _get_breakdown_row("ADR-excluded rows (hon. Members, stage directions)", 0, "  0.00%"),
        _get_breakdown_row("rows with no speaker", 4, " 40.00%"),
        _get_breakdown_row("reports with no rows", 0, "  0.00%"),
        _get_breakdown_row("dropped inside reports with rows (preamble, headings, labels)", 1, " 10.00%"),
    ]


@pytest.mark.parametrize(
    ("linked_character_count", "body_total", "expected_percent"),
    [(3, 3, "100.00%"), (1, 3000, "  0.03%"), (1, 10, " 10.00%")],
)
def test_breakdown_percent_keeps_its_width(
    monkeypatch: pytest.MonkeyPatch,
    logged_messages: list[str],
    linked_character_count: int,
    body_total: int,
    expected_percent: str,
) -> None:
    category_to_character_count = Counter({LINKED_CATEGORY: linked_character_count})
    _log_figures(monkeypatch, _get_group_figures(Counter(), category_to_character_count, body_total))

    linked_row = _get_breakdown_rows(logged_messages)[0]
    assert linked_row == _get_breakdown_row("linked rows", linked_character_count, expected_percent)
