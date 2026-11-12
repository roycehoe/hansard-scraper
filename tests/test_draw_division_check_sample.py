import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

import scripts.draw_division_check_sample as draw_division_check_sample_script
from database.division import Division
from database.division_party_count import DivisionPartyCount
from database.division_vote import DivisionVote
from database.minutes import Minutes, MinutesIndexCapture
from database.minutes_division import MinutesDivision
from database.report import Report
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
from exceptions import HansardDivisionCheckError
from schemas.division_check_sample import (
    DivisionCheckCandidate,
    DivisionCheckKey,
    DivisionCheckPacket,
)
from settings import settings
from tests.division_seed import add_division_report, add_division_speech_rows
from tests.refresh_fixtures import build_live_index_page, build_live_index_row

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
_SHORT_OUTSIDE_COUNT = 2
_COPY_BATCH_COUNT = 2
_MAX_BATCH_PACKETS = 100
_BATCH_TEST_PACKET_COUNT = 150
_MAX_BATCH_CHARACTERS = 160_000
_HALF_BATCH_CLAIM = "Ayes 10, Noes 3"
_ONE_SIDED_CLAIM = "AYE: Mr A\nAYE: Mr B"
_OTHER_SEED = 8
_TABLES = (Division, Minutes, MinutesDivision, DivisionVote, DivisionPartyCount)
_INDEX_SITTING_DATE = date(2021, 10, 5)
_INDEX_FILE_ID = "file-7"
_INDEX_FILE_NAME = "VP 7.pdf"
_INDEX_FILE_URL = f"{settings.minutes_media_url}/{_INDEX_FILE_ID}/VP%207.pdf"
_INDEX_LABEL = "Votes and Proceedings No. 7"
_INDEX_PARLIAMENT = "14th Parliament"
_ARCHIVE_INDEX_FIXTURE = (
    Path(__file__).parent
    / "division_fixtures"
    / "minutes_index"
    / "archive-index-2021-08.html"
)
_ARCHIVE_INDEX_TIMESTAMP = "20210912134436"
_ARCHIVE_SITTING_DATE = date(2021, 8, 3)
_ARCHIVE_LABEL = "Votes and Proceedings No. 36"
_ARCHIVE_FILE_URL = "https://www.parliament.gov.sg/docs/default-source/default-document-library/vp-3aug21.pdf?sfvrsn=aa9ad958_0"
_SIDE_CLAIM = "AYE: Mr A\nNO: Mr B"
_SWAPPED_SIDE_CLAIM = "AYE: Mr B\nNO: Mr A"
_ABSENT_VOTE_ORDINAL = 50
_PRE_ERA_CONTENT = "The House divided: Ayes, 10; Noes, 3.<pre>Ayes  Noes</pre>"
_REFUSED_PRINTED_LIST = "Ayes: Mr A Mr B Mr C."


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

    assert [
        (candidate.source_text, candidate.data_claim) for candidate in candidates
    ] == [("Mr Lee", f"{_SPEAKER_NAME} | Parliament {_PARLIAMENT_NUMBER}")]


def test_a_draw_takes_fifty_per_group_and_repeats_with_the_same_seed() -> None:
    candidates = [_build_candidate(key) for key in range(_GROUP_SIZE)]
    candidates.append(_build_candidate(_GROUP_SIZE, group="2010s|bill"))

    first_draw = draw_division_check_sample_script.draw_candidates(candidates, _SEED)
    second_draw = draw_division_check_sample_script.draw_candidates(
        list(reversed(candidates)), _SEED
    )

    assert len(first_draw) == _ROWS_PER_GROUP + 1
    assert first_draw == second_draw


def test_each_rule_has_the_plant_kind_that_fits_its_claim() -> None:
    assert draw_division_check_sample_script.get_plant_kinds(
        DivisionCheckRule.INDEX_ROW
    ) == (DivisionCheckPlantKind.WRONG_DATE,)
    assert draw_division_check_sample_script.get_plant_kinds(
        DivisionCheckRule.FILE_HEAD_DATE
    ) == (DivisionCheckPlantKind.WRONG_DATE,)
    assert draw_division_check_sample_script.get_plant_kinds(
        DivisionCheckRule.PARTY_ON_DATE
    ) == (DivisionCheckPlantKind.WRONG_PARTY,)
    assert draw_division_check_sample_script.get_plant_kinds(
        DivisionCheckRule.PRINTED_LINE
    ) == (DivisionCheckPlantKind.WRONG_COUNT_DIGIT,)
    assert draw_division_check_sample_script.get_plant_kinds(
        DivisionCheckRule.NAME_TIER_HAND_LIST
    ) == (DivisionCheckPlantKind.WRONG_PERSON,)
    assert all(
        draw_division_check_sample_script.get_plant_kinds(rule)
        for rule in DivisionCheckRule
    )


def test_only_rules_with_packets_of_one_shape_share_plant_rows() -> None:
    assert draw_division_check_sample_script.get_sibling_rules(
        DivisionCheckRule.PRINTED_LINE
    ) == (DivisionCheckRule.SPOKEN_TOTAL,)
    assert set(
        draw_division_check_sample_script.get_sibling_rules(
            DivisionCheckRule.NAME_TIER_EXACT
        )
    ) == {
        DivisionCheckRule.NAME_TIER_INVERTED,
        DivisionCheckRule.NAME_TIER_BIN_FREE,
        DivisionCheckRule.NAME_TIER_SAME_WORDS,
        DivisionCheckRule.NAME_TIER_HAND_LIST,
    }
    assert (
        draw_division_check_sample_script.get_sibling_rules(DivisionCheckRule.PAIRING)
        == ()
    )


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


def _build_date_candidate(
    key: int, sitting_date: date, data_claim_tail: str = ""
) -> DivisionCheckCandidate:
    return _build_candidate(
        key, data_claim=f"sitting date {sitting_date}{data_claim_tail}"
    )


def test_a_wrong_date_plant_names_the_nearest_other_sitting_date() -> None:
    claimed = _build_date_candidate(1, date(2021, 10, 4), "; label V&P; address a")
    near = _build_date_candidate(2, date(2021, 10, 6))
    far = _build_date_candidate(3, date(2020, 1, 1))

    planted_claim = draw_division_check_sample_script.build_plant_claim(
        DivisionCheckPlantKind.WRONG_DATE, claimed, [claimed, far, near]
    )

    assert planted_claim == "sitting date 2021-10-06; label V&P; address a"
    assert (
        draw_division_check_sample_script.build_plant_claim(
            DivisionCheckPlantKind.WRONG_DATE, claimed, [claimed]
        )
        is None
    )


def test_a_wrong_party_plant_names_the_other_span_party_of_the_member() -> None:
    claimed = _build_candidate(1, data_claim="party WP, uncertain False").model_copy(
        update={
            "source_text": "Lee on 2021-10-04; ballot party PAP; spans: PAP from 2011-05-01 (DAY, upper bound False); WP from 2021-01-01 (MONTH, upper bound True)"
        }
    )
    other = _build_candidate(2, data_claim="party SDP, uncertain False")

    planted_claim = draw_division_check_sample_script.build_plant_claim(
        DivisionCheckPlantKind.WRONG_PARTY, claimed, [claimed, other]
    )

    assert planted_claim == "party PAP, uncertain False"


def test_a_wrong_party_plant_falls_back_to_another_party_of_the_frame() -> None:
    claimed = _build_candidate(1, data_claim="party PAP, uncertain True").model_copy(
        update={"source_text": "Lee on 2021-10-04; ballot party PAP; spans: none"}
    )
    other = _build_candidate(2, data_claim="party WP, uncertain False")

    assert (
        draw_division_check_sample_script.build_plant_claim(
            DivisionCheckPlantKind.WRONG_PARTY, claimed, [claimed, other]
        )
        == "party WP, uncertain True"
    )
    assert (
        draw_division_check_sample_script.build_plant_claim(
            DivisionCheckPlantKind.WRONG_PARTY, claimed, [claimed]
        )
        is None
    )


def test_a_wrong_pair_plant_can_fill_an_unpaired_claim() -> None:
    unpaired = _build_candidate(
        1, data_claim="pairing NO_MATCHING_DIVISION, no Hansard division paired"
    ).model_copy(update={"source_text": "Hansard divisions of the date:\n1. Ayes 10"})
    no_division_on_the_date = unpaired.model_copy(
        update={"source_text": "Hansard divisions of the date:"}
    )

    assert (
        draw_division_check_sample_script.build_plant_claim(
            DivisionCheckPlantKind.WRONG_PAIR, unpaired, [unpaired]
        )
        == "pairing PAIRED, Hansard division 1"
    )
    assert (
        draw_division_check_sample_script.build_plant_claim(
            DivisionCheckPlantKind.WRONG_PAIR,
            no_division_on_the_date,
            [no_division_on_the_date],
        )
        is None
    )


def test_a_kind_that_plants_nothing_is_refused() -> None:
    candidates = [
        _build_candidate(key, data_claim=_ONE_SIDED_CLAIM)
        for key in range(_SMALL_GROUP_SIZE)
    ]
    drawn_candidates = draw_division_check_sample_script.draw_candidates(
        candidates, _SEED
    )

    with pytest.raises(HansardDivisionCheckError, match="SWAPPED_SIDE"):
        draw_division_check_sample_script.draw_plants(
            candidates,
            drawn_candidates,
            (DivisionCheckPlantKind.SWAPPED_SIDE,),
            _SEED,
            list,
        )


def _draw_whole_frame_with_copied_plants() -> tuple[
    list[DivisionCheckCandidate],
    list[DivisionCheckCandidate],
    list[draw_division_check_sample_script.PlantedCandidate],
]:
    candidates = [_build_candidate(key) for key in range(_SMALL_GROUP_SIZE)]
    drawn_candidates = draw_division_check_sample_script.draw_candidates(
        candidates, _SEED
    )
    planted_candidates = draw_division_check_sample_script.draw_plants(
        candidates,
        drawn_candidates,
        (DivisionCheckPlantKind.WRONG_COUNT_DIGIT,),
        _SEED,
        list,
    )
    return candidates, drawn_candidates, planted_candidates


def test_a_frame_drawn_whole_with_no_sibling_rows_plants_copies_of_sampled_rows() -> (
    None
):
    candidates, drawn_candidates, planted_candidates = (
        _draw_whole_frame_with_copied_plants()
    )

    drawn_keys = {candidate.database_key for candidate in drawn_candidates}
    assert len(planted_candidates) == _PLANT_COUNT
    assert all(
        planted.candidate.database_key in drawn_keys for planted in planted_candidates
    )
    assert (
        len({planted.candidate.database_key for planted in planted_candidates})
        == _PLANT_COUNT
    )
    assert all(
        planted.planted_claim != planted.candidate.data_claim
        for planted in planted_candidates
    )
    lines = draw_division_check_sample_script.get_summary_lines(
        DivisionCheckRule.PRINTED_LINE,
        _SEED,
        "db",
        candidates,
        drawn_candidates,
        planted_candidates,
    )
    assert (
        f"plant kind {DivisionCheckPlantKind.WRONG_COUNT_DIGIT}: 5 planted, 0 from the frames of sibling rules, 5 copies of sampled rows"
        in lines
    )


def test_a_frame_short_of_outside_rows_takes_them_all_before_copying_sampled_rows() -> (
    None
):
    candidates = [
        _build_candidate(key) for key in range(_ROWS_PER_GROUP + _SHORT_OUTSIDE_COUNT)
    ]
    drawn_candidates = draw_division_check_sample_script.draw_candidates(
        candidates, _SEED
    )

    planted_candidates = draw_division_check_sample_script.draw_plants(
        candidates,
        drawn_candidates,
        (DivisionCheckPlantKind.WRONG_COUNT_DIGIT,),
        _SEED,
        list,
    )

    drawn_keys = {candidate.database_key for candidate in drawn_candidates}
    assert len(planted_candidates) == _PLANT_COUNT
    assert (
        sum(
            planted.candidate.database_key not in drawn_keys
            for planted in planted_candidates
        )
        == _SHORT_OUTSIDE_COUNT
    )
    assert (
        sum(
            planted.candidate.database_key in drawn_keys
            for planted in planted_candidates
        )
        == _PLANT_COUNT - _SHORT_OUTSIDE_COUNT
    )


def test_no_reader_batch_holds_a_sampled_row_and_its_copy() -> None:
    _, drawn_candidates, planted_candidates = _draw_whole_frame_with_copied_plants()
    packets_and_key = draw_division_check_sample_script.build_packets_and_key(
        DivisionCheckRule.PRINTED_LINE, _SEED, drawn_candidates, planted_candidates
    )

    batches = draw_division_check_sample_script.get_reader_batches(
        packets_and_key.packets, packets_and_key.key.packet_id_to_database_key
    )

    assert len(batches) == _COPY_BATCH_COUNT
    for batch in batches:
        batch_keys = [
            packets_and_key.key.packet_id_to_database_key[packet.packet_id]
            for packet in batch
        ]
        assert len(batch_keys) == len(set(batch_keys))
    assert sorted(packet.packet_id for batch in batches for packet in batch) == sorted(
        packet.packet_id for packet in packets_and_key.packets
    )


def test_a_reader_batch_holds_at_most_a_hundred_packets() -> None:
    drawn_candidates = [
        _build_candidate(key) for key in range(_BATCH_TEST_PACKET_COUNT)
    ]
    packets_and_key = draw_division_check_sample_script.build_packets_and_key(
        DivisionCheckRule.PRINTED_LINE, _SEED, drawn_candidates, []
    )

    batches = draw_division_check_sample_script.get_reader_batches(
        packets_and_key.packets, packets_and_key.key.packet_id_to_database_key
    )

    assert [len(batch) for batch in batches] == [
        _MAX_BATCH_PACKETS,
        _BATCH_TEST_PACKET_COUNT - _MAX_BATCH_PACKETS,
    ]


def test_a_reader_batch_holds_at_most_160000_characters() -> None:
    half_batch_packets = [
        DivisionCheckPacket(
            packet_id=f"packet-{key}",
            source_text="x" * (_MAX_BATCH_CHARACTERS // 2 - len(_HALF_BATCH_CLAIM)),
            data_claim=_HALF_BATCH_CLAIM,
        )
        for key in range(2)
    ]
    packets = [
        *half_batch_packets,
        DivisionCheckPacket(
            packet_id="packet-2", source_text="", data_claim=_HALF_BATCH_CLAIM
        ),
    ]

    batches = draw_division_check_sample_script.get_reader_batches(
        packets, {packet.packet_id: packet.packet_id for packet in packets}
    )

    assert [[packet.packet_id for packet in batch] for batch in batches] == [
        ["packet-0", "packet-1"],
        ["packet-2"],
    ]


def test_a_frame_drawn_whole_takes_its_plant_rows_from_a_sibling_frame() -> None:
    candidates = [_build_candidate(key) for key in range(_SMALL_GROUP_SIZE)]
    drawn_candidates = draw_division_check_sample_script.draw_candidates(
        candidates, _SEED
    )
    sibling_candidates = [
        _build_candidate(_GROUP_SIZE + key).model_copy(
            update={"rule": DivisionCheckRule.SPOKEN_TOTAL}
        )
        for key in range(_PLANT_COUNT)
    ]

    planted_candidates = draw_division_check_sample_script.draw_plants(
        candidates,
        drawn_candidates,
        (DivisionCheckPlantKind.WRONG_COUNT_DIGIT,),
        _SEED,
        lambda: sibling_candidates,
    )

    assert len(planted_candidates) == _PLANT_COUNT
    assert all(
        planted.candidate.rule == DivisionCheckRule.SPOKEN_TOTAL
        for planted in planted_candidates
    )


def test_a_frame_with_enough_outside_rows_reads_no_sibling_frame() -> None:
    candidates = [_build_candidate(key) for key in range(_GROUP_SIZE + _PLANT_COUNT)]
    drawn_candidates = draw_division_check_sample_script.draw_candidates(
        candidates, _SEED
    )

    def fail_on_sibling_read() -> list[DivisionCheckCandidate]:
        raise AssertionError("the sibling frame was read")

    planted_candidates = draw_division_check_sample_script.draw_plants(
        candidates,
        drawn_candidates,
        (DivisionCheckPlantKind.WRONG_COUNT_DIGIT,),
        _SEED,
        fail_on_sibling_read,
    )

    assert len(planted_candidates) == _PLANT_COUNT


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
        list,
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
        list,
    )

    packets_and_key = draw_division_check_sample_script.build_packets_and_key(
        DivisionCheckRule.PRINTED_LINE, _SEED, drawn_candidates, planted_candidates
    )

    packets = packets_and_key.packets
    assert len(packets) == _ROWS_PER_GROUP + _PLANT_COUNT
    assert all("division:" not in packet.model_dump_json() for packet in packets)
    assert len({packet.packet_id for packet in packets}) == len(packets)
    assert len(packets_and_key.key.plants) == _PLANT_COUNT
    assert set(packets_and_key.key.packet_id_to_database_key) == {
        packet.packet_id for packet in packets
    }


def test_the_summary_says_which_plant_kinds_the_rule_does_not_use() -> None:
    candidates = [_build_candidate(1)]
    sibling_planted = draw_division_check_sample_script.PlantedCandidate(
        _build_candidate(2).model_copy(update={"rule": DivisionCheckRule.SPOKEN_TOTAL}),
        DivisionCheckPlantKind.WRONG_COUNT_DIGIT,
        "Ayes 20, Noes 3",
    )

    lines = draw_division_check_sample_script.get_summary_lines(
        DivisionCheckRule.PRINTED_LINE,
        _SEED,
        "db",
        candidates,
        candidates,
        [sibling_planted],
    )

    assert (
        f"plant kind {DivisionCheckPlantKind.SWAPPED_SIDE}: not used for this rule"
        in lines
    )
    assert (
        f"plant kind {DivisionCheckPlantKind.WRONG_COUNT_DIGIT}: 1 planted, 1 from the frames of sibling rules, 0 copies of sampled rows"
        in lines
    )
    assert f"seed\t{_SEED}" in lines
    assert "database\tdb" in lines


def test_a_packet_holds_only_a_random_id_the_source_and_the_claim() -> None:
    assert set(DivisionCheckPacket.model_fields) == {
        "packet_id",
        "source_text",
        "data_claim",
    }


def test_the_written_key_hash_matches_the_key_file(tmp_path: Path) -> None:
    candidates = [_build_candidate(1)]
    packets_and_key = draw_division_check_sample_script.build_packets_and_key(
        DivisionCheckRule.PRINTED_LINE, _SEED, candidates, []
    )
    output_directory = tmp_path / "check"

    draw_division_check_sample_script.write_check_files(
        output_directory, packets_and_key.packets, packets_and_key.key, ["line"]
    )

    key_bytes = (output_directory / "key.json").read_bytes()
    assert (output_directory / "key.sha256").read_text().strip() == hashlib.sha256(
        key_bytes
    ).hexdigest()
    batch_packet_dicts = json.loads(
        (output_directory / "batches" / "batch-01" / "packets.json").read_text()
    )
    assert [packet_dict["packet_id"] for packet_dict in batch_packet_dicts] == [
        packets_and_key.packets[0].packet_id
    ]
    with pytest.raises(FileExistsError):
        draw_division_check_sample_script.write_check_files(
            output_directory, packets_and_key.packets, packets_and_key.key, ["line"]
        )


def _add_live_index_minutes(
    session: Session,
    stored_date: date,
    printed_date: date,
    stored_label: str = _INDEX_LABEL,
) -> Minutes:
    capture = MinutesIndexCapture(
        original_url=settings.minutes_index_url,
        capture_url=f"{settings.minutes_index_url}#sha256=draw-{stored_date}",
        content=build_live_index_page(
            [build_live_index_row(printed_date, 7, _INDEX_FILE_ID, _INDEX_FILE_NAME)]
        ),
    )
    session.add(capture)
    session.flush()
    minutes = Minutes(
        sitting_date=stored_date,
        printed_label=stored_label,
        printed_parliament=_INDEX_PARLIAMENT,
        file_url=_INDEX_FILE_URL,
        file_format=MinutesFileFormat.PDF,
        status=MinutesStatus.LISTED,
        index_source=MinutesIndexSource.LIVE_PAGE,
        index_capture_id=capture.id,
    )
    session.add(minutes)
    session.flush()
    return minutes


def _seed_every_frame(session: Session) -> None:
    speaker = Speaker(
        name=_SPEAKER_NAME,
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=_PARLIAMENT_NUMBER,
    )
    other_speaker = Speaker(
        name=_OTHER_SPEAKER_NAME,
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
        file_url="https://example.invalid/minutes.pdf",
        file_format=MinutesFileFormat.PDF,
        extracted_text="Votes and Proceedings of 4 October 2021",
        status=MinutesStatus.TEXT_STORED,
        index_source=MinutesIndexSource.ARCHIVE_FILE_LISTING,
    )
    session.add_all([speaker, other_speaker, printed_division, total_division, minutes])
    _add_live_index_minutes(session, _INDEX_SITTING_DATE, _INDEX_SITTING_DATE)
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
            speaker_id=None
            if name_rule is None
            else (speaker.id if ordinal % 2 else other_speaker.id),
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


@pytest.mark.parametrize("printed_absent_count", [None, 1])
def test_a_stored_list_with_absent_names_and_no_absent_count_takes_its_own_group(
    scratch_session: Session, printed_absent_count: Optional[int]
) -> None:
    _seed_every_frame(scratch_session)
    division = scratch_session.exec(
        select(Division).where(Division.printed_list == _PRINTED_LIST)
    ).one()
    division.absent = printed_absent_count
    scratch_session.add(
        DivisionVote(
            ordinal=_ABSENT_VOTE_ORDINAL,
            printed_name="Mr C",
            vote_choice=DivisionVoteChoice.ABSENT,
            list_source=DivisionVoteListSource.HANSARD,
            division_id=division.id,
        )
    )
    scratch_session.flush()

    candidates = draw_division_check_sample_script.get_division_check_candidates(
        scratch_session, DivisionCheckRule.HANSARD_LIST_BY_LAYOUT_ERA
    )

    candidate = next(
        candidate
        for candidate in candidates
        if candidate.database_key == f"division:{division.id}"
    )
    assert candidate.group.endswith("side without a printed count") == (
        printed_absent_count is None
    )
    assert (
        candidate.source_text == f"Printed count line: {_MERGE_LINE}\n{_PRINTED_LIST}"
    )


def test_a_refused_list_takes_a_group_of_its_own_beside_the_stored_lists_of_its_era(
    scratch_session: Session,
) -> None:
    _seed_every_frame(scratch_session)
    report = scratch_session.exec(
        select(Report).where(Report.report_id == _MERGE_REPORT_ID)
    ).one()
    report.content = _PRE_ERA_CONTENT
    stored_division = scratch_session.exec(
        select(Division).where(Division.printed_list == _PRINTED_LIST)
    ).one()
    refused_division = Division(
        sitting_date=_SITTING_DATE,
        parliament_number=_PARLIAMENT_NUMBER,
        report_division_number=2,
        speech_ordinal=2,
        count_source=DivisionCountSource.PRINTED_LINE,
        printed_counts=_MERGE_LINE,
        ayes=_AYES,
        noes=_NOES,
        list_status=DivisionListStatus.COUNTS_DISAGREE,
        printed_list=_REFUSED_PRINTED_LIST,
        sprs_report_id=_MERGE_REPORT_ID,
    )
    scratch_session.add_all([report, refused_division])
    scratch_session.flush()

    candidates = draw_division_check_sample_script.get_division_check_candidates(
        scratch_session, DivisionCheckRule.HANSARD_LIST_BY_LAYOUT_ERA
    )

    database_key_to_group = {
        candidate.database_key: candidate.group for candidate in candidates
    }
    assert database_key_to_group[f"division:{stored_division.id}"] == f"{_DECADE}|pre"
    assert (
        database_key_to_group[f"division:{refused_division.id}"]
        == f"{_DECADE}|pre|no vote rows"
    )


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
    assert not [
        candidate
        for candidate in candidates
        for report_id in (_MERGE_REPORT_ID, _TOTAL_REPORT_ID)
        if report_id in candidate.source_text or report_id in candidate.data_claim
    ]


def test_the_index_row_frame_reads_the_printed_date_and_address_of_the_capture(
    scratch_session: Session,
) -> None:
    _seed_every_frame(scratch_session)

    candidates = draw_division_check_sample_script.get_division_check_candidates(
        scratch_session, DivisionCheckRule.INDEX_ROW
    )

    assert [
        (candidate.group, candidate.source_text, candidate.data_claim)
        for candidate in candidates
    ] == [
        (
            "2020s|LIVE_PAGE|PDF",
            f"{_INDEX_LABEL}; date {_INDEX_SITTING_DATE.isoformat()}T12:00:00; {_INDEX_PARLIAMENT}; file {_INDEX_FILE_NAME}; links to {_INDEX_FILE_URL}",
            f"sitting date {_INDEX_SITTING_DATE}; label {_INDEX_LABEL}; address {_INDEX_FILE_URL}",
        )
    ]


def test_the_index_row_source_is_the_capture_and_the_claim_is_the_stored_row(
    scratch_session: Session,
) -> None:
    _add_live_index_minutes(
        scratch_session, _INDEX_SITTING_DATE, _INDEX_SITTING_DATE, "Stale label"
    )

    (candidate,) = draw_division_check_sample_script.get_division_check_candidates(
        scratch_session, DivisionCheckRule.INDEX_ROW
    )

    assert candidate.source_text.startswith(_INDEX_LABEL)
    assert "Stale label" in candidate.data_claim


def test_the_index_row_frame_reads_an_archive_capture_with_the_archive_parser(
    scratch_session: Session,
) -> None:
    capture = MinutesIndexCapture(
        original_url=settings.minutes_index_url,
        archive_timestamp=_ARCHIVE_INDEX_TIMESTAMP,
        capture_url=f"https://web.archive.org/web/{_ARCHIVE_INDEX_TIMESTAMP}/{settings.minutes_index_url}",
        content=_ARCHIVE_INDEX_FIXTURE.read_text(encoding="utf-8"),
    )
    scratch_session.add(capture)
    scratch_session.flush()
    scratch_session.add(
        Minutes(
            sitting_date=_ARCHIVE_SITTING_DATE,
            printed_label=_ARCHIVE_LABEL,
            printed_parliament=_INDEX_PARLIAMENT,
            file_url=_ARCHIVE_FILE_URL,
            archive_timestamp=_ARCHIVE_INDEX_TIMESTAMP,
            file_format=MinutesFileFormat.PDF,
            status=MinutesStatus.LISTED,
            index_source=MinutesIndexSource.ARCHIVE_INDEX_CAPTURE,
            index_capture_id=capture.id,
        )
    )
    scratch_session.flush()

    candidates = draw_division_check_sample_script.get_division_check_candidates(
        scratch_session, DivisionCheckRule.INDEX_ROW
    )

    assert [
        (candidate.group, candidate.source_text, candidate.data_claim)
        for candidate in candidates
    ] == [
        (
            "2020s|ARCHIVE_INDEX_CAPTURE|PDF",
            f"{_ARCHIVE_LABEL} Sitting on 3 August 2021 {_INDEX_PARLIAMENT}; links to {_ARCHIVE_FILE_URL}",
            f"sitting date {_ARCHIVE_SITTING_DATE}; label {_ARCHIVE_LABEL}; address {_ARCHIVE_FILE_URL}",
        )
    ]


def _add_division_on_report(
    session: Session, report_id: str, speech_number: int, title: str
) -> Division:
    report = add_division_report(
        session, report_id, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    report.speech_number = speech_number
    report.title = title
    division = Division(
        sitting_date=_SITTING_DATE,
        parliament_number=_PARLIAMENT_NUMBER,
        report_division_number=1,
        speech_ordinal=1,
        count_source=DivisionCountSource.PRINTED_LINE,
        printed_counts=_MERGE_LINE,
        ayes=_AYES,
        noes=_NOES,
        list_status=DivisionListStatus.NOT_PRINTED,
        sprs_report_id=report_id,
    )
    session.add(division)
    session.flush()
    return division


def test_the_pairing_frame_lists_the_date_in_the_order_the_rule_pairs(
    scratch_session: Session,
) -> None:
    later_division = _add_division_on_report(
        scratch_session, "pairing-later", 5, "Later debate"
    )
    earlier_division = _add_division_on_report(
        scratch_session, "pairing-earlier", 2, "Earlier debate"
    )
    minutes = Minutes(
        sitting_date=_SITTING_DATE,
        file_format=MinutesFileFormat.PDF,
        status=MinutesStatus.TEXT_STORED,
    )
    scratch_session.add(minutes)
    scratch_session.flush()
    assert minutes.id is not None
    scratch_session.add_all(
        MinutesDivision(
            ordinal=ordinal,
            printed_counts=f"Minutes counts {ordinal}",
            ayes=_AYES,
            noes=_NOES,
            list_status=DivisionListStatus.NOT_PRINTED,
            pairing=MinutesDivisionPairing.PAIRED,
            minutes_id=minutes.id,
            division_id=division.id,
        )
        for ordinal, division in ((1, earlier_division), (2, later_division))
    )
    scratch_session.flush()

    candidates = draw_division_check_sample_script.get_division_check_candidates(
        scratch_session, DivisionCheckRule.PAIRING
    )

    first_candidate = next(
        candidate
        for candidate in candidates
        if candidate.source_text.count("(this one): Minutes counts 1") == 1
    )
    assert first_candidate.source_text.split("\n") == [
        "Minutes of 2021-10-04, divisions in order:",
        "Minutes division 1 (this one): Minutes counts 1",
        "Minutes division 2: Minutes counts 2",
        "Hansard divisions of the date, in order of report speech number and row:",
        f"1. {_MERGE_LINE} (Earlier debate, speech 2, row 1)",
        f"2. {_MERGE_LINE} (Later debate, speech 5, row 1)",
    ]
    assert first_candidate.data_claim == "pairing PAIRED, Hansard division 1"
    assert {candidate.data_claim for candidate in candidates} == {
        "pairing PAIRED, Hansard division 1",
        "pairing PAIRED, Hansard division 2",
    }


def test_a_stored_date_the_capture_does_not_print_shows_the_printed_date_to_the_reader(
    scratch_session: Session,
) -> None:
    _add_live_index_minutes(scratch_session, _SITTING_DATE, _INDEX_SITTING_DATE)

    (candidate,) = draw_division_check_sample_script.get_division_check_candidates(
        scratch_session, DivisionCheckRule.INDEX_ROW
    )

    assert f"date {_INDEX_SITTING_DATE.isoformat()}" in candidate.source_text
    assert f"sitting date {_SITTING_DATE}" in candidate.data_claim


def test_an_index_row_whose_address_the_capture_does_not_print_is_refused(
    scratch_session: Session,
) -> None:
    minutes = _add_live_index_minutes(
        scratch_session, _INDEX_SITTING_DATE, _INDEX_SITTING_DATE
    )
    minutes.file_url = f"{settings.minutes_media_url}/another-file/VP%208.pdf"
    scratch_session.flush()

    with pytest.raises(HansardDivisionCheckError, match="matches 0 rows"):
        draw_division_check_sample_script.get_division_check_candidates(
            scratch_session, DivisionCheckRule.INDEX_ROW
        )


def test_a_merged_division_with_no_speech_row_is_refused_by_name(
    scratch_session: Session,
) -> None:
    merge_report = add_division_report(
        scratch_session, _MERGE_REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    add_division_speech_rows(
        scratch_session,
        merge_report,
        [
            (SpeechKind.PROCEDURAL, None, _MERGE_LINE),
            (SpeechKind.SPEECH, None, _MERGE_TOTAL),
        ],
    )
    scratch_session.add(
        Division(
            sitting_date=_SITTING_DATE,
            parliament_number=_PARLIAMENT_NUMBER,
            report_division_number=1,
            speech_ordinal=None,
            count_source=DivisionCountSource.PRINTED_LINE,
            printed_counts=_MERGE_LINE,
            ayes=_AYES,
            noes=_NOES,
            list_status=DivisionListStatus.NOT_PRINTED,
            sprs_report_id=_MERGE_REPORT_ID,
        )
    )
    scratch_session.flush()

    with pytest.raises(HansardDivisionCheckError, match="holds no speech row"):
        draw_division_check_sample_script.get_division_check_candidates(
            scratch_session, DivisionCheckRule.PRINTED_AND_SPOKEN_MERGE
        )


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
    key = DivisionCheckKey.model_validate_json(
        (tmp_path / "check" / "key.json").read_text()
    )
    assert key.plants
    packet_dicts = json.loads((tmp_path / "check" / "packets.json").read_text())
    assert packet_dicts
    assert all(
        set(packet_dict) == {"packet_id", "source_text", "data_claim"}
        for packet_dict in packet_dicts
    )
    batch_packet_ids = [
        packet_dict["packet_id"]
        for batch_file in sorted(
            (tmp_path / "check" / "batches").glob("batch-*/packets.json")
        )
        for packet_dict in json.loads(batch_file.read_text())
    ]
    assert sorted(batch_packet_ids) == sorted(
        packet_dict["packet_id"] for packet_dict in packet_dicts
    )


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
