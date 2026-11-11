import hashlib
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

import scripts.draw_division_check_sample as draw_division_check_sample_script
from database.division import Division
from database.division_party_count import DivisionPartyCount
from database.division_vote import DivisionVote
from database.minutes import Minutes
from database.minutes_division import MinutesDivision
from database.speaker import Speaker
from enums import (
    DivisionCheckPlantKind,
    DivisionCheckRule,
    DivisionCountSource,
    DivisionListStatus,
    DivisionVoteChoice,
    DivisionVoteListSource,
    DivisionVoteNameRule,
    MinutesDivisionPairing,
    MinutesFileFormat,
    MinutesIndexSource,
    MinutesStatus,
    SpeechKind,
)
from schemas.division_check_sample import DivisionCheckCandidate
from tests.division_seed import add_division_report, add_division_speech_rows

_SITTING_DATE = date(2021, 10, 4)
_SITTING_DATETIME = datetime(2021, 10, 4)
_PARLIAMENT_NUMBER = 14
_REPORT_ID = "draw-report"
_SEED = 7
_GROUP_SIZE = 60
_ROWS_PER_GROUP = 50
_PLANT_COUNT = 5
_AYES = 10
_NOES = 3
_PRINTED_LINE = "The House divided: Ayes, 10; Noes, 3"
_SPEAKER_NAME = "Lee Hsien Loong"
_OTHER_SPEAKER_NAME = "Heng Swee Keat"
_MERGE_REPORT_ID = "draw-merge-report"
_TOTAL_REPORT_ID = "draw-total-report"
_MERGE_LINE = "The House divided: Ayes, 10; Noes, 3."
_MERGE_TOTAL = "There are 10 Ayes and 3 Noes."
_PRINTED_LIST = "Ayes: Mr A. Noes: Mr B."
_DECADE = "2020s"
_SMALL_GROUP_SIZE = 10
_OTHER_SEED = 8
_TABLES = (Division, Minutes, MinutesDivision, DivisionVote, DivisionPartyCount)
_SIDE_CLAIM = "AYE: Mr A\nNO: Mr B"
_SWAPPED_SIDE_CLAIM = "AYE: Mr B\nNO: Mr A"


def _build_candidate(
    key: int, group: str = "2020s|bill", data_claim: str = "Ayes 10, Noes 3"
) -> DivisionCheckCandidate:
    return DivisionCheckCandidate(
        rule=DivisionCheckRule.PRINTED_LINE,
        group=group,
        source_text=f"source {key}",
        data_claim=data_claim,
        database_key=f"division:{key}",
    )


def test_a_printed_line_candidate_carries_the_row_and_its_counts(
    scratch_session: Session,
) -> None:
    report = add_division_report(
        scratch_session, _REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    add_division_speech_rows(
        scratch_session, report, [(SpeechKind.PROCEDURAL, None, _PRINTED_LINE)]
    )
    scratch_session.add(
        Division(
            sitting_date=_SITTING_DATE,
            parliament_number=_PARLIAMENT_NUMBER,
            report_division_number=1,
            speech_ordinal=1,
            count_source=DivisionCountSource.PRINTED_LINE,
            printed_counts=_PRINTED_LINE,
            ayes=_AYES,
            noes=_NOES,
            list_status=DivisionListStatus.NOT_PRINTED,
            sprs_report_id=_REPORT_ID,
        )
    )
    scratch_session.flush()

    candidates = draw_division_check_sample_script.get_division_check_candidates(
        scratch_session, DivisionCheckRule.PRINTED_LINE
    )

    assert [
        (candidate.group, candidate.source_text, candidate.data_claim)
        for candidate in candidates
    ] == [
        (
            "2020s|bill",
            _PRINTED_LINE,
            "Ayes 10, Noes 3, Abstentions None, Absent None, Paired None",
        )
    ]


def test_a_name_tier_candidate_claims_the_linked_person(
    scratch_session: Session,
) -> None:
    speaker = Speaker(
        name=_SPEAKER_NAME,
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=_PARLIAMENT_NUMBER,
    )
    division = Division(
        sitting_date=_SITTING_DATE,
        parliament_number=_PARLIAMENT_NUMBER,
        count_source=DivisionCountSource.MINUTES,
        printed_counts=_PRINTED_LINE,
        ayes=_AYES,
        noes=_NOES,
        list_status=DivisionListStatus.STORED,
    )
    scratch_session.add_all([speaker, division])
    scratch_session.flush()
    scratch_session.add_all(
        [
            DivisionVote(
                ordinal=1,
                printed_name="Mr Lee",
                vote_choice=DivisionVoteChoice.AYE,
                list_source=DivisionVoteListSource.MINUTES,
                name_rule=DivisionVoteNameRule.EXACT,
                division_id=division.id,
                speaker_id=speaker.id,
            ),
            DivisionVote(
                ordinal=2,
                printed_name="Mr Lee",
                vote_choice=DivisionVoteChoice.NO,
                list_source=DivisionVoteListSource.MINUTES,
                name_rule=DivisionVoteNameRule.INVERTED,
                division_id=division.id,
                speaker_id=speaker.id,
            ),
        ]
    )
    scratch_session.flush()

    candidates = draw_division_check_sample_script.get_division_check_candidates(
        scratch_session, DivisionCheckRule.NAME_TIER_EXACT
    )

    assert [(candidate.source_text, candidate.data_claim) for candidate in candidates] == [
        ("Mr Lee", f"{_SPEAKER_NAME} | Parliament {_PARLIAMENT_NUMBER}")
    ]


def test_a_draw_takes_fifty_per_group_and_repeats_with_the_same_seed() -> None:
    candidates = [_build_candidate(key) for key in range(_GROUP_SIZE)]
    candidates.append(_build_candidate(_GROUP_SIZE, group="2010s|bill"))

    first_draw = draw_division_check_sample_script.draw_candidates(candidates, _SEED)
    second_draw = draw_division_check_sample_script.draw_candidates(
        list(reversed(candidates)), _SEED
    )

    assert len(first_draw) == _ROWS_PER_GROUP + 1
    assert first_draw == second_draw


def test_a_rule_without_a_field_to_break_gets_no_plant_kind() -> None:
    assert draw_division_check_sample_script.get_plant_kinds(
        DivisionCheckRule.INDEX_ROW
    ) == ()
    assert draw_division_check_sample_script.get_plant_kinds(
        DivisionCheckRule.PRINTED_LINE
    ) == (DivisionCheckPlantKind.WRONG_COUNT_DIGIT,)
    assert draw_division_check_sample_script.get_plant_kinds(
        DivisionCheckRule.NAME_TIER_HAND_LIST
    ) == (DivisionCheckPlantKind.WRONG_PERSON,)


def test_a_wrong_count_digit_plant_changes_the_claim() -> None:
    candidate = _build_candidate(1)

    planted_claim = draw_division_check_sample_script.build_plant_claim(
        DivisionCheckPlantKind.WRONG_COUNT_DIGIT, candidate, [candidate]
    )

    assert planted_claim == "Ayes 20, Noes 3"


def test_a_swapped_side_plant_trades_two_names_between_sides() -> None:
    candidate = _build_candidate(1, data_claim=_SIDE_CLAIM)
    one_sided_candidate = _build_candidate(2, data_claim="AYE: Mr A\nAYE: Mr B")

    assert (
        draw_division_check_sample_script.build_plant_claim(
            DivisionCheckPlantKind.SWAPPED_SIDE, candidate, [candidate]
        )
        == _SWAPPED_SIDE_CLAIM
    )
    assert (
        draw_division_check_sample_script.build_plant_claim(
            DivisionCheckPlantKind.SWAPPED_SIDE,
            one_sided_candidate,
            [one_sided_candidate],
        )
        is None
    )


def test_a_wrong_person_plant_names_another_person_of_the_same_parliament() -> None:
    first_candidate = _build_candidate(
        1, data_claim=f"{_SPEAKER_NAME} | Parliament {_PARLIAMENT_NUMBER}"
    )
    second_candidate = _build_candidate(
        2, data_claim=f"{_OTHER_SPEAKER_NAME} | Parliament {_PARLIAMENT_NUMBER}"
    )

    planted_claim = draw_division_check_sample_script.build_plant_claim(
        DivisionCheckPlantKind.WRONG_PERSON,
        first_candidate,
        [first_candidate, second_candidate],
    )

    assert planted_claim == second_candidate.data_claim


def test_plants_come_from_rows_outside_the_sample() -> None:
    candidates = [_build_candidate(key) for key in range(_GROUP_SIZE + _PLANT_COUNT)]
    drawn_candidates = draw_division_check_sample_script.draw_candidates(
        candidates, _SEED
    )

    planted_candidates = draw_division_check_sample_script.draw_plants(
        candidates,
        drawn_candidates,
        (DivisionCheckPlantKind.WRONG_COUNT_DIGIT,),
        _SEED,
    )

    drawn_keys = {candidate.database_key for candidate in drawn_candidates}
    assert len(planted_candidates) == _PLANT_COUNT
    assert all(
        planted.candidate.database_key not in drawn_keys
        for planted in planted_candidates
    )


def test_the_packets_show_no_database_key_and_the_key_names_each_plant() -> None:
    candidates = [_build_candidate(key) for key in range(_GROUP_SIZE + _PLANT_COUNT)]
    drawn_candidates = draw_division_check_sample_script.draw_candidates(
        candidates, _SEED
    )
    planted_candidates = draw_division_check_sample_script.draw_plants(
        candidates,
        drawn_candidates,
        (DivisionCheckPlantKind.WRONG_COUNT_DIGIT,),
        _SEED,
    )

    packets, key = draw_division_check_sample_script.build_packets_and_key(
        DivisionCheckRule.PRINTED_LINE, _SEED, drawn_candidates, planted_candidates
    )

    assert len(packets) == _ROWS_PER_GROUP + _PLANT_COUNT
    assert all("division:" not in packet.model_dump_json() for packet in packets)
    assert len({packet.packet_id for packet in packets}) == len(packets)
    assert len(key.plants) == _PLANT_COUNT
    assert set(key.packet_id_to_database_key) == {packet.packet_id for packet in packets}


def test_the_summary_says_which_plant_kinds_the_rule_skipped() -> None:
    candidates = [_build_candidate(1)]

    lines = draw_division_check_sample_script.get_summary_lines(
        DivisionCheckRule.INDEX_ROW, _SEED, "db", candidates, candidates, []
    )

    assert (
        f"plant kind {DivisionCheckPlantKind.SWAPPED_SIDE}: skipped, the rule has no field for it"
        in lines
    )


def test_the_written_key_hash_matches_the_key_file(tmp_path: Path) -> None:
    candidates = [_build_candidate(1)]
    packets, key = draw_division_check_sample_script.build_packets_and_key(
        DivisionCheckRule.PRINTED_LINE, _SEED, candidates, []
    )
    output_directory = tmp_path / "check"

    draw_division_check_sample_script.write_check_files(
        output_directory, packets, key, ["line"]
    )

    key_bytes = (output_directory / "key.json").read_bytes()
    assert (output_directory / "key.sha256").read_text().strip() == hashlib.sha256(
        key_bytes
    ).hexdigest()
    with pytest.raises(FileExistsError):
        draw_division_check_sample_script.write_check_files(
            output_directory, packets, key, ["line"]
        )


def _seed_every_frame(session: Session) -> None:
    speaker = Speaker(
        name=_SPEAKER_NAME,
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=_PARLIAMENT_NUMBER,
    )
    merge_report = add_division_report(
        session, _MERGE_REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    total_report = add_division_report(
        session, _TOTAL_REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    add_division_speech_rows(
        session,
        merge_report,
        [
            (SpeechKind.PROCEDURAL, None, _MERGE_LINE),
            (SpeechKind.SPEECH, None, _MERGE_TOTAL),
        ],
    )
    add_division_speech_rows(
        session, total_report, [(SpeechKind.SPEECH, None, _MERGE_TOTAL)]
    )
    printed_division = Division(
        sitting_date=_SITTING_DATE,
        parliament_number=_PARLIAMENT_NUMBER,
        report_division_number=1,
        speech_ordinal=1,
        count_source=DivisionCountSource.PRINTED_LINE,
        printed_counts=_MERGE_LINE,
        ayes=_AYES,
        noes=_NOES,
        list_status=DivisionListStatus.STORED,
        printed_list=_PRINTED_LIST,
        sprs_report_id=_MERGE_REPORT_ID,
    )
    total_division = Division(
        sitting_date=_SITTING_DATE,
        parliament_number=_PARLIAMENT_NUMBER,
        report_division_number=1,
        speech_ordinal=1,
        count_source=DivisionCountSource.SPOKEN_TOTAL,
        printed_counts=_MERGE_TOTAL,
        ayes=_AYES,
        noes=_NOES,
        list_status=DivisionListStatus.NOT_PRINTED,
        sprs_report_id=_TOTAL_REPORT_ID,
    )
    minutes = Minutes(
        sitting_date=_SITTING_DATE,
        printed_label="Votes and Proceedings",
        printed_parliament=str(_PARLIAMENT_NUMBER),
        file_url="https://example.invalid/minutes.pdf",
        file_format=MinutesFileFormat.PDF,
        extracted_text="Votes and Proceedings of 4 October 2021",
        status=MinutesStatus.TEXT_STORED,
        index_source=MinutesIndexSource.ARCHIVE_FILE_LISTING,
    )
    session.add_all([speaker, printed_division, total_division, minutes])
    session.flush()
    session.add(
        MinutesDivision(
            ordinal=1,
            printed_counts=_MERGE_LINE,
            ayes=_AYES,
            noes=_NOES,
            printed_list=_PRINTED_LIST,
            list_status=DivisionListStatus.STORED,
            pairing=MinutesDivisionPairing.PAIRED,
            minutes_id=minutes.id,
            division_id=printed_division.id,
        )
    )
    session.add_all(
        DivisionVote(
            ordinal=ordinal,
            printed_name="Mr A",
            vote_choice=vote_choice,
            list_source=list_source,
            name_rule=name_rule,
            party=None if name_rule is None else "PAP",
            division_id=printed_division.id,
            speaker_id=None if name_rule is None else speaker.id,
        )
        for list_source, name_rules in (
            (DivisionVoteListSource.HANSARD, list(DivisionVoteNameRule)),
            (DivisionVoteListSource.MINUTES, [None, None]),
        )
        for ordinal, name_rule in enumerate(name_rules, 1)
        for vote_choice in [
            DivisionVoteChoice.AYE if ordinal % 2 else DivisionVoteChoice.NO
        ]
    )
    session.flush()


@pytest.mark.parametrize("rule", list(DivisionCheckRule))
def test_each_rule_has_a_frame_that_reads_a_seeded_database(
    scratch_session: Session, rule: DivisionCheckRule
) -> None:
    _seed_every_frame(scratch_session)

    candidates = draw_division_check_sample_script.get_division_check_candidates(
        scratch_session, rule
    )

    assert candidates
    assert all(candidate.rule == rule for candidate in candidates)
    assert all(candidate.group.startswith(f"{_DECADE}|") for candidate in candidates)


def _count_rows(session: Session) -> list[int]:
    return [
        session.exec(select(func.count()).select_from(table)).one() for table in _TABLES
    ]


def test_the_script_writes_nothing_to_the_database(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_every_frame(scratch_session)
    scratch_session.commit()
    monkeypatch.setattr(
        draw_division_check_sample_script,
        "build_read_only_engine",
        lambda database_url: scratch_engine,
    )
    row_counts_before = _count_rows(scratch_session)
    assert all(row_count > 0 for row_count in row_counts_before[:-1])

    draw_division_check_sample_script.draw_division_check_sample(
        DivisionCheckRule.NAME_TIER_EXACT, _SEED, tmp_path / "check"
    )

    scratch_session.expire_all()
    assert _count_rows(scratch_session) == row_counts_before
    assert (tmp_path / "check" / "packets.json").exists()


def test_the_script_refuses_an_existing_output_directory(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_every_frame(scratch_session)
    scratch_session.commit()
    monkeypatch.setattr(
        draw_division_check_sample_script,
        "build_read_only_engine",
        lambda database_url: scratch_engine,
    )
    (tmp_path / "check").mkdir()

    with pytest.raises(FileExistsError):
        draw_division_check_sample_script.draw_division_check_sample(
            DivisionCheckRule.NAME_TIER_EXACT, _SEED, tmp_path / "check"
        )

    assert not (tmp_path / "check" / "packets.json").exists()


def test_a_group_of_sixty_draws_fifty_and_a_group_of_ten_is_taken_whole() -> None:
    candidates = [_build_candidate(key) for key in range(_GROUP_SIZE)]
    candidates.extend(
        _build_candidate(_GROUP_SIZE + key, group="2010s|bill")
        for key in range(_SMALL_GROUP_SIZE)
    )

    drawn_candidates = draw_division_check_sample_script.draw_candidates(
        candidates, _SEED
    )

    assert [
        sum(candidate.group == group for candidate in drawn_candidates)
        for group in ("2020s|bill", "2010s|bill")
    ] == [_ROWS_PER_GROUP, _SMALL_GROUP_SIZE]


def test_the_same_seed_gives_the_same_draw_and_another_seed_a_different_one() -> None:
    candidates = [_build_candidate(key) for key in range(_GROUP_SIZE)]

    first_draw = draw_division_check_sample_script.draw_candidates(candidates, _SEED)
    same_seed_draw = draw_division_check_sample_script.draw_candidates(
        candidates, _SEED
    )
    other_seed_draw = draw_division_check_sample_script.draw_candidates(
        candidates, _OTHER_SEED
    )

    assert first_draw == same_seed_draw
    assert first_draw != other_seed_draw
