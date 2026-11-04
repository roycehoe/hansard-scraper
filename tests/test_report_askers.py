from dataclasses import replace
from typing import Optional

import pytest

from crud.speech import SpeechAskerRow
from enums import ReportAskerSource, SpeechKind
from services.report_asker import (
    build_report_askers,
    get_asker_candidates,
    get_question_row_ordinals,
)
from utils.asker_candidate import AskerCandidate

_REPORT_ID = 1


def _build_row(
    ordinal: int,
    kind: Optional[SpeechKind],
    speaker: Optional[str],
    speaker_id: Optional[int],
    transcript: str,
) -> SpeechAskerRow:
    return SpeechAskerRow(
        id=ordinal,
        report_id=_REPORT_ID,
        ordinal=ordinal,
        speaker=speaker,
        transcript=transcript,
        kind=kind,
        speaker_id=speaker_id,
    )


_REPORT_38033_STOOD_ROW = _build_row(
    1,
    SpeechKind.UNCLASSIFIED,
    None,
    None,
    "The following Question stood in the name of -",
)


def test_stood_line_credits_the_filer_and_swallows_the_filers_to_ask_row() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.PROCEDURAL,
            None,
            None,
            "The following question stood in the name of Dr Tan Wu Meng –",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Dr Tan Wu Meng",
            1224,
            "5 To ask the Minister for Health (a) whether vendors providing motorised mobility devices",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Christopher de Souza (Holland-Bukit Timah)",
            1144,
            "Question No 5.",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "The Minister of State for Health (Ms Rahayu Mahzam) (for the Minister for Finance)",
            1210,
            "Mr Speaker, the Seniors' Mobility and Enabling Fund (SMF) and Assistive Technology Fund",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Dr Tan Wu Meng",
            speaker_id=None,
            reader_printed_name="Mr Christopher de Souza (Holland-Bukit Timah)",
            reader_speaker_id=1144,
            reader_row_ordinal=3,
        )
    ]


def test_stood_line_over_unclassified_rows_takes_the_member_who_reads_the_number() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following question stood in the name of Dr Lim Wee Kiak –",
        ),
        _build_row(
            2,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "5 To ask the Minister for Trade and Industry (a) what is the Ministry doing to ensure",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Ms Denise Phua Lay Peng (Jalan Besar)",
            1148,
            "Question No 5.",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "The Second Minister for Trade and Industry (Dr Tan See Leng) (for the Minister for Trade and Industry)",
            1227,
            "Since the start of the year, global oil prices and domestic pump prices have been rising",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Dr Lim Wee Kiak",
            speaker_id=None,
            reader_printed_name="Ms Denise Phua Lay Peng (Jalan Besar)",
            reader_speaker_id=1148,
            reader_row_ordinal=3,
        )
    ]


def test_stood_line_before_a_document_text_question_takes_the_reader_of_its_number() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Question stood in the name of Dr Ahmad Mohd Magad –",
        ),
        _build_row(
            2,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "2. To ask the Minister for Health since the implementation of the Human Organ Transplant Act",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mdm Halimah Yacob (Jurong)",
            824,
            "Question No. 2, Sir.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Dr Ahmad Mohd Magad",
            speaker_id=None,
            reader_printed_name="Mdm Halimah Yacob (Jurong)",
            reader_speaker_id=824,
            reader_row_ordinal=3,
        )
    ]


def test_read_out_on_behalf_of_the_filer_is_the_reader() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.PROCEDURAL,
            None,
            None,
            "The following question stood in the name of Ms Kuik Shiao-Yin –",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Ms Kuik Shiao-Yin",
            1068,
            "23 To ask the Minister for Home Affairs (a) why does Singapore support the criminalisation of suicide",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Azmoon Ahmad (Nominated Member)",
            1022,
            "On behalf of Ms Kuik, Question No 23.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Ms Kuik Shiao-Yin",
            speaker_id=None,
            reader_printed_name="Mr Azmoon Ahmad (Nominated Member)",
            reader_speaker_id=1022,
            reader_row_ordinal=3,
        )
    ]


def test_read_out_that_opens_with_mr_speaker_is_the_reader() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.PROCEDURAL,
            None,
            None,
            "The following question stood in the name of Mr Zainudin Nordin –",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr Zainudin Nordin",
            1016,
            "12 To ask the Minister for Education (a) how many ITE students are currently receiving financial assistance",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Zaqy Mohamad (Chua Chu Kang)",
            1017,
            "Mr Speaker, Question No 12, please.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mr Zainudin Nordin",
            speaker_id=None,
            reader_printed_name="Mr Zaqy Mohamad (Chua Chu Kang)",
            reader_speaker_id=1017,
            reader_row_ordinal=3,
        )
    ]


def test_read_out_with_a_different_number_is_no_reader() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.PROCEDURAL,
            None,
            None,
            "The following question stood in the name of Dr Tan Wu Meng –",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Dr Tan Wu Meng",
            1224,
            "5 To ask the Minister for Health (a) whether vendors providing motorised mobility devices",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Christopher de Souza (Holland-Bukit Timah)",
            1144,
            "Question No 6.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Dr Tan Wu Meng",
            speaker_id=None,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        )
    ]


def test_stood_candidate_comes_before_another_members_asked_row_and_keeps_the_reader() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.PROCEDURAL,
            None,
            None,
            "The following question stood in the name of Mr Saktiandi Supaat –",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr Saktiandi Supaat",
            1212,
            "43 To ask the Minister for Digital Development and Information (a) whether the Ministry is aware",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Chua Kheng Wee Louis",
            1146,
            "asked the Minister for Digital Development and Information in light of the whistle-blowing report",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "Dr Tan Wu Meng (Jurong)",
            1224,
            "Question No 43.",
        ),
        _build_row(
            5,
            SpeechKind.SPEECH,
            "The Senior Minister of State for Digital Development and Information (Mr Tan Kiat How) (for the Minister for Digital Development and Information)",
            1226,
            "Mr Speaker, may I have your permission to address Question Nos 43 and 74 for oral answer",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mr Saktiandi Supaat",
            speaker_id=None,
            reader_printed_name="Dr Tan Wu Meng (Jurong)",
            reader_speaker_id=1224,
            reader_row_ordinal=4,
        ),
        AskerCandidate(
            row_ordinal=3,
            source=ReportAskerSource.ASKED_LINE,
            printed_name="Mr Chua Kheng Wee Louis",
            speaker_id=1146,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        ),
    ]


def test_stood_line_with_no_question_row_takes_the_first_read_out_when_no_number_is_known() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Question stood in the name of Dr Muhammad Faishal Ibrahim - 5. To ask the Deputy Prime Minister and Minister for Home Affairs whether",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr Sam Tan Chin Siong (Tanjong Pagar)",
            884,
            "Question No. 5, Sir.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Dr Muhammad Faishal Ibrahim",
            speaker_id=None,
            reader_printed_name="Mr Sam Tan Chin Siong (Tanjong Pagar)",
            reader_speaker_id=884,
            reader_row_ordinal=2,
        )
    ]


def test_stood_line_takes_no_reader_from_beyond_the_next_stood_line() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Question stood in the name of Dr Muhammad Faishal Ibrahim - 5. To ask the Deputy Prime Minister and Minister for Home Affairs whether",
        ),
        _build_row(
            2,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Question stood in the name of Mdm Halimah Yacob - 5. To ask the Deputy Prime Minister and Minister for Home Affairs (a) whether",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Yeo Guat Kwang (Aljunied)",
            800,
            "Question No. 5.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Dr Muhammad Faishal Ibrahim",
            speaker_id=None,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        ),
        AskerCandidate(
            row_ordinal=2,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mdm Halimah Yacob",
            speaker_id=None,
            reader_printed_name="Mr Yeo Guat Kwang (Aljunied)",
            reader_speaker_id=800,
            reader_row_ordinal=3,
        ),
    ]


_ABSENT_FILER_READ_OUT_TRANSCRIPTS = [
    "Mr Speaker, Sir, since the Member for Potong Pasir is not here, I ask Question No. 4.",
    "Sir, I have been asked by the Member for Mountbatten to raise Question No. 2.",
    "Sir, I have been requested by the Member for Mount-batten to ask Question No. 3.",
    "Sir, I have been asked by Mr Teong Eng Siong to raise Question No. 2.",
    "Sir, I have been asked by Mr Ch'ng Jit Koon to raise question No. 3.",
    "Mr Speaker, Sir, in the absence of Mr P. Govindaswamy, may I ask Question No. 1?",
    "Mr Speaker, Sir, as Mr Chia Thye Poh is not here, I am asking this question on his behalf.",
    "Mr Speaker, Sir, in the absence of Madam Chan Choy Sion, may I ask Question No. 20?",
    "As Mr Poh Ber Liak is absent, I would like to put the question to the Minister for Labour.",
]
_NOT_ABSENT_FILER_READ_OUT_TRANSCRIPTS = [
    "Mr Speaker, Sir, I have been asked by my Minister to reply.",
    "Sir, I have been asked by the Prime Minister to reply to this question.",
    "I have been asked by the Minister to answer.",
    "Mr Speaker, Sir, I have been requested by the Hon. the Prime Minister to reply to the question.",
    "Mr Speaker, Sir, I have been asked by my colleague, the Minister for Labour, to reply",
    "In the absence of AMD, doctors may also recommend the treatment.",
    "In the absence of a donee or deputy, the doctor-in-charge decides.",
]


def _get_reader_printed_name(transcript: str) -> Optional[str]:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Question stood in the name of Mr Filer Name -",
        ),
        _build_row(2, SpeechKind.SPEECH, "Mr Stand In", 1, transcript),
    ]

    return get_asker_candidates(speech_asker_rows)[0].reader_printed_name


@pytest.mark.parametrize("transcript", _ABSENT_FILER_READ_OUT_TRANSCRIPTS)
def test_row_that_says_the_filer_is_absent_is_the_reader(transcript: str) -> None:
    assert _get_reader_printed_name(transcript) == "Mr Stand In"


@pytest.mark.parametrize("transcript", _NOT_ABSENT_FILER_READ_OUT_TRANSCRIPTS)
def test_row_that_names_a_minister_or_no_member_is_not_the_reader(
    transcript: str,
) -> None:
    assert _get_reader_printed_name(transcript) is None


def test_report_35981_member_asked_by_the_member_for_mountbatten_is_the_reader() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Question stood in the name of Mr Ng Yeow Chong -",
        ),
        _build_row(
            2,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "2. To ask the Minister for Law and National Development when work will commence on the construction of a hawkers' emporium and high-rise flats on a site in Old Kallang Airport Estate which was cleared for redevelopment in early 1970, and whether the flats will include 5-room units.",
        ),
        _build_row(
            3,
            SpeechKind.CHAMBER_EVENT,
            None,
            None,
            "Mr Hwang Soo Jin (Jalan Kayu) rose -",
        ),
        _build_row(4, SpeechKind.SPEECH, "Mr Speaker", 127, "Mr Hwang Soo Jin."),
        _build_row(
            5,
            SpeechKind.SPEECH,
            "Mr Hwang Soo Jin",
            87,
            "Sir, I have been asked by the Member for Mountbatten to raise Question No. 2.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mr Ng Yeow Chong",
            speaker_id=None,
            reader_printed_name="Mr Hwang Soo Jin",
            reader_speaker_id=87,
            reader_row_ordinal=5,
        )
    ]


def test_report_37878_member_asking_in_the_absence_of_the_filer_is_the_reader() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Question stood in the name of Mr P. Govindaswamy ---",
        ),
        _build_row(
            2,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "1. To ask the Minister for Law and National Development whether the Government is aware that during heavy rains Cheng Cheok Street and Tapah Street are flooded and whether the Government has any plans to remedy the situation.",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Ng Yeow Chong (Mountbatten)",
            42,
            "Mr Speaker, Sir, in the absence of Mr P. Govindaswamy, may I ask Question No. 1?",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mr P. Govindaswamy",
            speaker_id=None,
            reader_printed_name="Mr Ng Yeow Chong (Mountbatten)",
            reader_speaker_id=42,
            reader_row_ordinal=3,
        )
    ]


def test_report_38031_member_who_puts_the_question_because_the_filer_is_absent_is_the_reader() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Question stood in the name of Mr Poh Ber Liak :-",
        ),
        _build_row(
            2,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "13. To ask the Minister for Labour if he will make a statement on the strike of workers at Hup Seng Bee-Hoon Factory at Changi Road, 10 m.s., in July, 1965.",
        ),
        _build_row(
            3,
            SpeechKind.CHAMBER_EVENT,
            None,
            None,
            "Inche Mohd. Ariff Bin Suradi (Kampong Kembangan) rose ---",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "Mr Ho See Beng (Bras Basah)",
            25,
            "A supplementary question, Sir.",
        ),
        _build_row(
            5,
            SpeechKind.SPEECH,
            "Mr Speaker",
            2,
            "Order. Mr Ho, you are somewhat late. I have called the Question. Inche Mohd. Ariff.",
        ),
        _build_row(
            6,
            SpeechKind.SPEECH,
            "Inche Mohd. Ariff Bin Suradi",
            40,
            "As Mr Poh Ber Liak is absent, I would like to put the question to the Minister for Labour.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mr Poh Ber Liak",
            speaker_id=None,
            reader_printed_name="Inche Mohd. Ariff Bin Suradi",
            reader_speaker_id=40,
            reader_row_ordinal=6,
        )
    ]


def test_minister_saying_he_was_asked_by_my_minister_to_reply_is_not_the_reader() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Question stood in the name of Mr Poh Ber Liak :-",
        ),
        _build_row(
            2,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "13. To ask the Minister for Labour if he will make a statement on the strike of workers.",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Jek Yeun Thong",
            26,
            "Mr Speaker, Sir, I have been asked by my Minister to reply.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mr Poh Ber Liak",
            speaker_id=None,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        )
    ]


def test_numbered_read_out_is_preferred_over_an_earlier_absent_filer_read_out() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Question stood in the name of Mr Poh Ber Liak :-",
        ),
        _build_row(
            2,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "13. To ask the Minister for Labour if he will make a statement on the strike of workers.",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Ho See Beng (Bras Basah)",
            25,
            "As Mr Poh Ber Liak is absent, I would like to put the question to the Minister for Labour.",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "Inche Mohd. Ariff Bin Suradi",
            40,
            "Question No. 13, Sir.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mr Poh Ber Liak",
            speaker_id=None,
            reader_printed_name="Inche Mohd. Ariff Bin Suradi",
            reader_speaker_id=40,
            reader_row_ordinal=4,
        )
    ]


def test_absent_filer_read_out_beyond_the_next_stood_line_is_no_reader() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Question stood in the name of Mr Poh Ber Liak :-",
        ),
        _build_row(
            2,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Question stood in the name of Mr Teong Eng Siong :-",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Inche Mohd. Ariff Bin Suradi",
            40,
            "As Mr Teong Eng Siong is absent, I would like to put the question to the Minister for Labour.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert [
        (asker_candidate.printed_name, asker_candidate.reader_speaker_id)
        for asker_candidate in asker_candidates
    ] == [("Mr Poh Ber Liak", None), ("Mr Teong Eng Siong", 40)]


def test_stood_line_naming_three_filers_credits_each_and_a_filer_reading_out_is_no_reader() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Questions stood in the names of Ms Indranee Rajah, Mr Ong Kian Min and Mdm Ho Geok Choo respectively -",
        ),
        _build_row(
            2,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "9. To ask the Deputy Prime Minister and Minister for Home Affairs whether the Immigration and Checkpoints Authority",
        ),
        _build_row(
            3,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "10. To ask the Deputy Prime Minister and Minister for Home Affairs (a) what are the causes of the long queues",
        ),
        _build_row(
            4,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "11. To ask the Deputy Prime Minister and Minister for Home Affairs (a) how will the Immigration and Checkpoints Authority",
        ),
        _build_row(
            5,
            SpeechKind.SPEECH,
            "Mr Ong Kian Min (Tampines)",
            773,
            "Question No. 9, Sir.",
        ),
        _build_row(
            6,
            SpeechKind.SPEECH,
            "The Senior Minister of State for Home Affairs (Assoc. Prof. Ho Peng Kee) (for the Deputy Prime Minister and Minister for Home Affairs)",
            732,
            "Mr Speaker, Sir, can I have your permission to take Question Nos. 9 to 11 together",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name=printed_name,
            speaker_id=None,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        )
        for printed_name in (
            "Ms Indranee Rajah",
            "Mr Ong Kian Min",
            "Mdm Ho Geok Choo",
        )
    ]


def test_stood_over_question_credits_the_filer_with_no_reader() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Question stood in the name of Mr Ng Kah Ting -",
        ),
        _build_row(
            2,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "14. To ask the Minister for Education whether all students who pass the Primary School Leaving Examination",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Speaker",
            16,
            "Mr Ng has asked that Question No. 14* be stood over. Mr Ho Kah Leong.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mr Ng Kah Ting",
            speaker_id=None,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        )
    ]


def test_stood_line_that_prints_no_name_credits_no_one() -> None:
    speech_asker_rows = [
        _REPORT_38033_STOOD_ROW,
        _build_row(
            2,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "6. To ask the Minister for Education how many children have been registered for admission",
        ),
        _build_row(3, SpeechKind.SPEECH, "Mr Speaker", 2, "Mr Koo Young."),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == []


def test_stood_line_that_prints_no_name_leaves_the_next_to_ask_row_to_its_own_member() -> (
    None
):
    speech_asker_rows = [
        _REPORT_38033_STOOD_ROW,
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr Koo Young",
            77,
            "6. To ask the Minister for Education how many children have been registered for admission",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=2,
            source=ReportAskerSource.TO_ASK_LINE,
            printed_name="Mr Koo Young",
            speaker_id=77,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        )
    ]


def test_report_38368_footnote_stood_lines_with_a_dash_credit_both_filers() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr Speaker",
            1352,
            "Questions 1* and 2+ have been postponed to 29th July, 1963.",
        ),
        _build_row(
            2,
            SpeechKind.EDITORIAL_NOTE,
            None,
            None,
            "*Question No. 1 stood in the name of Mr Low Por Tuck -",
        ),
        _build_row(
            3,
            SpeechKind.EDITORIAL_NOTE,
            None,
            None,
            "To ask the Prime Minister who were the members of the Singapore team that attended",
        ),
        _build_row(
            4,
            SpeechKind.EDITORIAL_NOTE,
            None,
            None,
            "+Question No. 2 stood in the name of Mr Tee Kim Leng -",
        ),
        _build_row(
            5,
            SpeechKind.EDITORIAL_NOTE,
            None,
            None,
            "To ask the Prime Minister what is the progress in negotiations on the question of compensation",
        ),
        _build_row(
            6,
            SpeechKind.SPEECH,
            "Mr Ong Chang Sam",
            1383,
            "asked the Minister for Finance what progress has been made in the action taken against bogus insurance companies",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=2,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mr Low Por Tuck",
            speaker_id=None,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        ),
        AskerCandidate(
            row_ordinal=4,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mr Tee Kim Leng",
            speaker_id=None,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        ),
        AskerCandidate(
            row_ordinal=6,
            source=ReportAskerSource.ASKED_LINE,
            printed_name="Mr Ong Chang Sam",
            speaker_id=1383,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        ),
    ]


def test_stood_line_name_ends_before_text_that_runs_on() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr Chng Hee Kok",
            618,
            "The following Question stood in the name of Mr Chng Hee Kok- 11. To ask the Minister for Trade and Industry",
        )
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mr Chng Hee Kok",
            speaker_id=None,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        )
    ]


def test_stood_name_keeps_its_trailing_dot() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following question stood in the name of Mr Heng Chiang Meng.",
        ),
        _build_row(
            2,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "2. To ask the Minister for National Development whether the new policy of giving a cash grant",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Dr Ho Tat Kin (Boon Teck)",
            370,
            "Question 2, Sir.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mr Heng Chiang Meng.",
            speaker_id=None,
            reader_printed_name="Dr Ho Tat Kin (Boon Teck)",
            reader_speaker_id=370,
            reader_row_ordinal=3,
        )
    ]


def test_asked_row_right_after_a_stood_line_is_kept_and_the_reader_follows_it() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following question stood in the name of Ms Denise Phua Lay Peng",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Ms Denise Phua Lay Peng",
            920,
            "asked the Acting Minister for Community Development, Youth and Sports if there is a recommended approach",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mrs Lina Chiam",
            916,
            "asked the Acting Minister for Community Development, Youth and Sports with regard to the $61 million",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "Er Dr Lee Bee Wah",
            954,
            "Question 1, Sir.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Ms Denise Phua Lay Peng",
            speaker_id=None,
            reader_printed_name="Er Dr Lee Bee Wah",
            reader_speaker_id=954,
            reader_row_ordinal=4,
        ),
        AskerCandidate(
            row_ordinal=2,
            source=ReportAskerSource.ASKED_LINE,
            printed_name="Ms Denise Phua Lay Peng",
            speaker_id=920,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        ),
        AskerCandidate(
            row_ordinal=3,
            source=ReportAskerSource.ASKED_LINE,
            printed_name="Mrs Lina Chiam",
            speaker_id=916,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        ),
    ]


def test_name_in_a_row_without_a_speaker_credits_the_named_member() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "Mr S. V. Lingam asked the Minister of Defence if he will consider the construction of a Community Centre",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "The Minister of Defence (Dr Goh Keng Swee)",
            20,
            "Mr Speaker, Sir, the Government has no plans to construct a community centre",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.NAME_IN_TEXT,
            printed_name="Mr S. V. Lingam",
            speaker_id=None,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        )
    ]


def test_name_in_text_is_never_taken_from_a_row_that_has_a_speaker() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Dr Goh Keng Swee",
            20,
            "Mr S. V. Lingam asked the Minister of Defence if he will consider the construction of a Community Centre",
        )
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == []


def test_name_in_text_that_is_the_speaker_credits_no_one() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "Mr Speaker asked the Minister of Defence if he will consider the construction of a Community Centre",
        )
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == []


def test_asked_line_run_together_as_askedthe_credits_the_member() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Dr Benedict Tan",
            994,
            "askedthe Minister for Health whether the latest salary review for public sector doctors has succeeded",
        )
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.ASKED_LINE,
            printed_name="Dr Benedict Tan",
            speaker_id=994,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        )
    ]


def test_asked_line_after_a_private_notice_marker_credits_the_member() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mrs Seow Peck Leng",
            1377,
            "(by Private Notice under Standing Order No. 18 (1) asked the Minister for Education (i) whether he is aware",
        )
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.ASKED_LINE,
            printed_name="Mrs Seow Peck Leng",
            speaker_id=1377,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        )
    ]


def test_ask_the_minister_line_credits_the_member() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Ms Sylvia Lim",
            882,
            "ask the Minister for Manpower (a) in 2009, how many complaints were made to the Ministry",
        )
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.ASKED_LINE,
            printed_name="Ms Sylvia Lim",
            speaker_id=882,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        )
    ]


def test_asked_line_with_no_kind_credits_the_member() -> None:
    speech_asker_rows = [
        _build_row(1, None, "(Rationale)", None, ""),
        _build_row(
            2,
            None,
            "Mr Inderjit Singh",
            830,
            "asked the Minister for Finance (a) what is the rationale for the billion-dollar investments by GIC and",
        ),
        _build_row(
            3,
            None,
            "Mr Inderjit Singh",
            830,
            "Temasek Holdings in distressed banks like UBS and Merrill Lynch; (b) whether it was too early",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=2,
            source=ReportAskerSource.ASKED_LINE,
            printed_name="Mr Inderjit Singh",
            speaker_id=830,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        )
    ]


def test_to_ask_row_labelled_mr_speaker_after_a_stood_line_credits_only_the_filer() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr Speaker",
            424,
            "Question No. 1 will be asked at 2.00 o'clock this afternoon.",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr Speaker",
            424,
            "The following question stood in the name of Mr Chiam See Tong -",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Speaker",
            424,
            "2. To ask the Minister for Trade and Industry if he will state the reasons for his change of mind",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "Dr Aline K. Wong",
            415,
            "Question No. 2, Sir.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=2,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mr Chiam See Tong",
            speaker_id=None,
            reader_printed_name="Dr Aline K. Wong",
            reader_speaker_id=415,
            reader_row_ordinal=4,
        )
    ]


def test_to_ask_row_labelled_mr_speaker_with_no_stood_line_credits_no_one() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr David Marshall",
            1349,
            "asked the Prime Minister what is the estimated expenditure of the part of the Singapore Government",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr Speaker",
            1352,
            "The questions standing in the name of Mr David Marshall read as follows:-",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Speaker",
            1352,
            "* 14. To ask the Prime Minister (a) what is the total payment to be made to the Johore Government",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "Mr Speaker",
            1352,
            "+ 15. To ask the Prime Minister (a) what is the estimated payment to be made by the Johore Government",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.ASKED_LINE,
            printed_name="Mr David Marshall",
            speaker_id=1349,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        )
    ]


def test_second_to_ask_row_of_a_stood_block_is_its_own_candidate() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.PROCEDURAL,
            None,
            None,
            "The following questions stood in the name of Mr R Dhinakaran –",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr R Dhinakaran",
            987,
            "3 To ask the Acting Minister for Manpower (a) whether Filipino and Sri Lankan construction workers",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr R Dhinakaran",
            987,
            "4 To ask the Acting Minister for Manpower in light of better-skilled Filipino construction workers",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "Mr Patrick Tay Teck Guan (Nee Soon)",
            984,
            "Question No 3, Madam.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name="Mr R Dhinakaran",
            speaker_id=None,
            reader_printed_name="Mr Patrick Tay Teck Guan (Nee Soon)",
            reader_speaker_id=984,
            reader_row_ordinal=4,
        ),
        AskerCandidate(
            row_ordinal=3,
            source=ReportAskerSource.TO_ASK_LINE,
            printed_name="Mr R Dhinakaran",
            speaker_id=987,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        ),
    ]


def test_to_ask_rows_that_stood_over_after_an_asked_row_credit_no_one() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr Cheong Yuen Chee",
            205,
            "asked the Minister for Law, the Environment and Science and Technology what measures are being taken to prevent further occurrences of contaminated food",
        ),
        _build_row(
            9,
            SpeechKind.SPEECH,
            "Mr Speaker",
            270,
            "Pursuant to Standing Order 21(2), the following Questions on the Order Paper accordingly stood over to the next available sitting of Parliament.",
        ),
        _build_row(
            10,
            SpeechKind.SPEECH,
            "Mr S. Dhanabalan",
            249,
            "To ask the Minister for Home Affairs and Education how many drug rehabilitation centres there are in Singapore",
        ),
        _build_row(
            11,
            SpeechKind.SPEECH,
            "Mr Teo Chong Tee",
            263,
            "To ask the Minister for Home Affairs and Education if part-time National Servicemen residing in Pulau Tekong can be assigned patrol duties",
        ),
    ]

    assert get_asker_candidates(speech_asker_rows) == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.ASKED_LINE,
            printed_name="Mr Cheong Yuen Chee",
            speaker_id=205,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        ),
    ]


def test_addendum_text_that_says_a_member_asked_credits_no_one() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "ADDENDA VACANT POSTS IN GOVERNMENT SERVICE HELD BY OFFICERS IN ACTING CAPACITY",
        ),
        _build_row(
            2,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "Dr Goh Keng Swee, pursuant to his reply to the following question for oral answer asked on 21st September, 1960",
        ),
        _build_row(
            3,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "Inche Mohd. Ali Bin Alwi asked the Minister for Finance to state the number of vacant posts",
        ),
        _build_row(
            4,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "supplied the following answer on 8th November, 1960:",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates == []


def test_build_report_askers_keeps_the_first_row_of_a_member_who_asked_twice() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Ms Carrie Tan",
            1222,
            "asked the Minister for National Development (a) how many cases of complex water seepage cases",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Ms Carrie Tan",
            1222,
            "asked the Minister for National Development (a) what is the current expected operating timeline",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Liang Eng Hwa",
            1183,
            "asked the Minister for National Development (a) whether there has been a surge in the number",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "Mr Liang Eng Hwa",
            1183,
            "asked the Minister for National Development (a) whether there is an update on the implementation",
        ),
        _build_row(
            5,
            SpeechKind.SPEECH,
            "The Senior Minister of State for National Development (Ms Sim Ann) (for the Minister for National Development)",
            1218,
            "Mr Speaker, Sir, may I have your permission to give a combined reply to Question Nos 3 through 6",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)
    report_askers = build_report_askers(_REPORT_ID, asker_candidates)

    assert [asker_candidate.row_ordinal for asker_candidate in asker_candidates] == [
        1,
        2,
        3,
        4,
    ]
    assert [
        (
            report_asker.report_id,
            report_asker.ordinal,
            report_asker.printed_name,
            report_asker.source,
            report_asker.speaker_id,
        )
        for report_asker in report_askers
    ] == [
        (_REPORT_ID, 1, "Ms Carrie Tan", ReportAskerSource.ASKED_LINE, 1222),
        (_REPORT_ID, 2, "Mr Liang Eng Hwa", ReportAskerSource.ASKED_LINE, 1183),
    ]


def test_build_report_askers_keeps_the_stood_candidate_with_its_reader_ahead_of_a_later_row() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.PROCEDURAL,
            None,
            None,
            "The following questions stood in the name of Mr R Dhinakaran –",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr R Dhinakaran",
            987,
            "3 To ask the Acting Minister for Manpower (a) whether Filipino and Sri Lankan construction workers",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr R Dhinakaran",
            987,
            "4 To ask the Acting Minister for Manpower in light of better-skilled Filipino construction workers",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "Mr Patrick Tay Teck Guan (Nee Soon)",
            984,
            "Question No 3, Madam.",
        ),
    ]
    stood_candidate, to_ask_candidate = get_asker_candidates(speech_asker_rows)

    report_askers = build_report_askers(
        _REPORT_ID, [replace(stood_candidate, speaker_id=987), to_ask_candidate]
    )

    assert [
        (
            report_asker.ordinal,
            report_asker.source,
            report_asker.speaker_id,
            report_asker.reader_printed_name,
            report_asker.reader_speaker_id,
        )
        for report_asker in report_askers
    ] == [
        (
            1,
            ReportAskerSource.STOOD_IN_NAME_LINE,
            987,
            "Mr Patrick Tay Teck Guan (Nee Soon)",
            984,
        )
    ]


def test_build_report_askers_keeps_an_unresolved_name_once_and_apart_from_other_names() -> (
    None
):
    asker_candidates = [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.NAME_IN_TEXT,
            printed_name="Mr S. V. Lingam",
            speaker_id=None,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        ),
        AskerCandidate(
            row_ordinal=2,
            source=ReportAskerSource.NAME_IN_TEXT,
            printed_name="Mr G. A. P. Sutherland",
            speaker_id=None,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        ),
        AskerCandidate(
            row_ordinal=3,
            source=ReportAskerSource.NAME_IN_TEXT,
            printed_name="Mr S. V. Lingam",
            speaker_id=None,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        ),
    ]

    report_askers = build_report_askers(_REPORT_ID, asker_candidates)

    assert [
        (report_asker.ordinal, report_asker.printed_name)
        for report_asker in report_askers
    ] == [(1, "Mr S. V. Lingam"), (2, "Mr G. A. P. Sutherland")]


def test_question_row_ordinals_hold_a_stood_line_that_prints_no_name_and_the_row_after_it() -> (
    None
):
    speech_asker_rows = [
        _REPORT_38033_STOOD_ROW,
        _build_row(
            2,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "6. To ask the Minister for Education how many children have been registered for admission",
        ),
        _build_row(3, SpeechKind.SPEECH, "Mr Speaker", 2, "Mr Koo Young."),
    ]

    assert get_question_row_ordinals(speech_asker_rows) == frozenset({1, 2})


def test_report_30113_question_row_ordinals_hold_a_to_ask_row_of_any_kind_and_a_labelled_read_out() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "6. To ask the Minister for the Environment which areas in Singapore have the highest number of food poisoning cases reported.",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Dr Aline K Wong (Tampines GRC)",
            500,
            "Question No. 6, Sir.",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Dr Ahmad Mattar",
            429,
            "Mr Speaker, Sir, a total of 120 incidents of food poisoning were reported during the first seven months of this year.",
        ),
    ]

    assert get_question_row_ordinals(speech_asker_rows) == frozenset({1, 2})


def test_report_37878_question_row_ordinals_hold_a_row_asking_in_the_absence_of_the_filer() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following Question stood in the name of Mr P. Govindaswamy ---",
        ),
        _build_row(
            2,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "1. To ask the Minister for Law and National Development whether the Government is aware that during heavy rains Cheng Cheok Street and Tapah Street are flooded.",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Ng Yeow Chong (Mountbatten)",
            42,
            "Mr Speaker, Sir, in the absence of Mr P. Govindaswamy, may I ask Question No. 1?",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "The Parliamentary Secretary to the Minister for National Development (Mr Ho Cheng Choon) (for the Minister for Law and National Development)",
            23,
            "Mr Speaker, Sir, the Government is aware that during heavy rains, Cheng Cheok Street and Tapah Street are flooded.",
        ),
    ]

    assert get_question_row_ordinals(speech_asker_rows) == frozenset({1, 2, 3})


def test_question_row_ordinals_leave_out_a_read_out_row_labelled_as_the_chair() -> None:
    speech_asker_rows = [
        _build_row(1, SpeechKind.SPEECH, "Mr Speaker", 2, "Question No. 6, Sir."),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Dr Ahmad Mattar",
            429,
            "Mr Speaker, Sir, a total of 120 incidents of food poisoning were reported.",
        ),
    ]

    assert get_question_row_ordinals(speech_asker_rows) == frozenset()


def test_report_25149_question_row_ordinals_leave_out_a_labelled_row_that_says_asked_the_mid_sentence() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr Gan Kim Yong",
            725,
            "asked the Minister for Health whether the proposed survey on the ElderShield Scheme has been",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr Lim Hng Kiang",
            752,
            "Mr Speaker, Sir, the Ministry has asked the two ElderShield insurers to consider doing a survey to",
        ),
    ]

    assert get_question_row_ordinals(speech_asker_rows) == frozenset({1})


def test_report_30105_stood_line_that_ends_the_report_credits_no_one() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Dr Lee Siew-Choh",
            50,
            "asked the Minister for National Development if he will make a statement concerning the arrears and penalty for non-payment of rent",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Dr Lee Boon Yang (for the Minister for National Development)",
            60,
            "Mr Speaker, Sir, the eating house, Chye Heng Cafeteria, in Block 401 Hougang Avenue 10, was recovered by HDB",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Dr Lee Boon Yang",
            60,
            "The following Question stood in the name of Mr Chiam See Tong -",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert [asker_candidate.printed_name for asker_candidate in asker_candidates] == [
        "Dr Lee Siew-Choh"
    ]


def test_report_title_that_lists_questions_stood_over_credits_no_one() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr Speaker",
            16,
            "Order. The following Questions for oral answer stood over.",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr Low Thia Khiang",
            70,
            "asked the Minister for Health whether the waiting time at polyclinics has changed",
        ),
    ]

    asker_candidates = get_asker_candidates(
        speech_asker_rows,
        "QUESTIONS FOR ORAL ANSWER STOOD OVER TO NEXT AVAILABLE SITTING OF PARLIAMENT",
    )

    assert asker_candidates == []


def test_report_20093_member_who_reads_out_the_number_of_a_to_ask_row_is_its_reader() -> (
    None
):
    speech_asker_rows = [
        _build_row(1, SpeechKind.SPEECH, "Mrs Lina Chiam", 916, "–"),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mrs Lina Chiam",
            916,
            "11To ask the Minister for Trade and Industry (a) what is the number of unlicensed tour guides caught during the last five years",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Patrick Tay Teck Guan",
            984,
            "asked the Minister for Trade and Industry (a) what is the annual number of unlicensed tour guides detected",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "Dr Lily Neo (Tanjong Pagar)",
            430,
            "Question No 11, Sir.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert asker_candidates[0] == AskerCandidate(
        row_ordinal=2,
        source=ReportAskerSource.TO_ASK_LINE,
        printed_name="Mrs Lina Chiam",
        speaker_id=916,
        reader_printed_name="Dr Lily Neo (Tanjong Pagar)",
        reader_speaker_id=430,
        reader_row_ordinal=4,
    )


def test_report_30113_numbered_question_printed_with_no_name_credits_no_one() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "6. To ask the Minister for the Environment which areas in Singapore have the highest number of food poisoning cases",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Dr Aline K Wong (Tampines GRC)",
            80,
            "Question No. 6, Sir.",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Dr Ahmad Mattar",
            90,
            "Mr Speaker, Sir, a total of 120 incidents of food poisoning were reported during the first seven months of this year",
        ),
    ]

    assert get_asker_candidates(speech_asker_rows) == []


def test_report_22632_several_unnumbered_to_ask_rows_before_one_read_out_have_no_reader() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "The following questions stood on the Order Paper -",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Dr Muhammad Faishal Ibrahim",
            310,
            "To ask the Minister for National Development with the rising prices of new and resale HDB flats",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Ms Eunice Elizabeth Olsen",
            311,
            "To ask the Minister for National Development whether his Ministry will consider raising the income ceiling",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "Mr Liang Eng Hwa (Holland-Bukit Timah)",
            312,
            "Question No. 8, Sir.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert [
        (asker_candidate.printed_name, asker_candidate.reader_speaker_id)
        for asker_candidate in asker_candidates
    ] == [
        ("Dr Muhammad Faishal Ibrahim", None),
        ("Ms Eunice Elizabeth Olsen", None),
    ]


def test_report_42459_chair_call_of_a_to_ask_filer_gives_the_read_out_its_filer() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Dr Aline K. Wong",
            415,
            "To ask the Acting Minister for Health (a) what is the type of Hepatitis B vaccine used in government hospitals",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Dr Ho Tat Kin",
            370,
            "To ask the Acting Minister for Health, in view of the worldwide concern over Aids",
        ),
        _build_row(3, SpeechKind.SPEECH, "Mr Deputy Speaker", 403, "Dr Aline Wong."),
        _build_row(
            4, SpeechKind.SPEECH, "Mr Chew Heng Ching", 358, "Question No. 20, Sir."
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert [
        (asker_candidate.printed_name, asker_candidate.reader_speaker_id)
        for asker_candidate in asker_candidates
    ] == [("Dr Aline K. Wong", 358), ("Dr Ho Tat Kin", None)]


def test_report_27568_member_who_reads_out_the_number_right_after_an_asked_row_is_its_reader() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr Tay Beng Chuan",
            681,
            "asked the Minister for Trade and Industry if he will give an assessment of the impact of the regional currency and financial crisis",
        ),
        _build_row(
            2, SpeechKind.SPEECH, "Mr Choo Wee Khiang", 620, "Question No. 11, Sir."
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Lee Yock Suan",
            646,
            "Mr Speaker, Sir, may I answer Question Nos. 11 and 12 together as they are related?",
        ),
    ]

    assert get_asker_candidates(speech_asker_rows) == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.ASKED_LINE,
            printed_name="Mr Tay Beng Chuan",
            speaker_id=681,
            reader_printed_name="Mr Choo Wee Khiang",
            reader_speaker_id=620,
            reader_row_ordinal=2,
        )
    ]


def test_report_35260_read_out_labelled_in_the_absence_of_the_filer_is_the_reader() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr Lee Kuan Yew",
            30,
            "asked the Chief Secretary (i) what is the object of the newly-formed Malayan Student Unit in England",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr M. P. D. Nair (in the absence of Mr Lee Kuan Yew)",
            1390,
            "Question No. 1.",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr J. D. Higham",
            1412,
            "The answer to the first part of the question is that the Unit is not a new organisation.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert [
        (asker_candidate.printed_name, asker_candidate.reader_speaker_id)
        for asker_candidate in asker_candidates
    ] == [("Mr Lee Kuan Yew", 1390)]


def test_report_32508_read_out_after_the_chairs_call_that_opens_with_mr_deputy_speaker_is_the_reader() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr Sia Kah Hui",
            328,
            "To ask the Minister for National Development if he will justify the increase by the Housing and Development Board",
        ),
        _build_row(2, SpeechKind.SPEECH, "Mr Deputy Speaker", 298, "Question No. 2."),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Ng Kah Ting (Punggol)",
            316,
            "Mr Deputy Speaker, Sir, Question No. 2.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert [
        (asker_candidate.printed_name, asker_candidate.reader_speaker_id)
        for asker_candidate in asker_candidates
    ] == [("Mr Sia Kah Hui", 316)]


def test_report_24068_several_asked_rows_before_one_read_out_have_no_reader() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mdm Ho Geok Choo",
            731,
            "asked the Minister for Trade and Industry if he will update the House on the progress of the Government's review",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Assoc. Prof. Ong Soh Khim",
            775,
            "asked the Minister for Trade and Industry (a) whether Government tax revenue is the only economic factor",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Assoc. Prof. Ong Soh Khim",
            775,
            "asked the Minister for Trade and Industry, as much of the scenario planning is theoretical",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "Dr Amy Khor Lean Suan (Hong Kah)",
            739,
            "Question No. 1, Sir.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert [
        (asker_candidate.printed_name, asker_candidate.reader_speaker_id)
        for asker_candidate in asker_candidates
    ] == [
        ("Mdm Ho Geok Choo", None),
        ("Assoc. Prof. Ong Soh Khim", None),
        ("Assoc. Prof. Ong Soh Khim", None),
    ]


def test_asked_row_answered_before_a_call_of_the_next_question_has_no_reader() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr Pritam Singh",
            1102,
            "asked the Minister for Health what the plans are for polyclinics.",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "The Minister for Health (Mr Gan Kim Yong)",
            700,
            "Mr Speaker, Sir, there are no plans for new polyclinics this year.",
        ),
        _build_row(
            3, SpeechKind.SPEECH, "Ms Sylvia Lim (Aljunied)", 1110, "Question No 13."
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "Ms Sylvia Lim (Aljunied)",
            1110,
            "asked the Minister for Law whether the courts have enough judges.",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert [
        (asker_candidate.printed_name, asker_candidate.reader_speaker_id)
        for asker_candidate in asker_candidates
    ] == [("Mr Pritam Singh", None), ("Ms Sylvia Lim (Aljunied)", None)]


def test_report_27802_filer_who_reads_out_his_own_question_under_another_printed_name_is_no_reader() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr J.B. Jeyaretnam",
            638,
            "asked the Minister for Home Affairs if he will inform the House of the provisions of the law",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr J. B. Jeyaretnam (Non-Constituency Member)",
            638,
            "Mr Speaker, Sir, Question 1. But before that is answered, may I say that I have no pecuniary interest",
        ),
    ]

    asker_candidates = get_asker_candidates(speech_asker_rows)

    assert [
        (asker_candidate.printed_name, asker_candidate.reader_speaker_id)
        for asker_candidate in asker_candidates
    ] == [("Mr J.B. Jeyaretnam", None)]


def test_report_20181_answerer_name_on_every_row_credits_no_one() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr Gan Kim Yong",
            930,
            "asked the Minister for Health for each of the last three years the HAI rate.",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr Gan Kim Yong",
            930,
            "Leading health experts in the world recommend targeted surveillance.",
        ),
    ]

    assert get_asker_candidates(speech_asker_rows) == []


def test_report_37816_answerer_label_inside_a_row_keeps_the_asker() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr S. V. Lingam",
            37,
            "asked the Deputy Prime Minister whether he will consider revising the postage.",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr S. V. Lingam",
            37,
            "Dr Toh Chin Chye : The postage rate on inland letters was raised to 15 cents.",
        ),
    ]

    assert get_asker_candidates(speech_asker_rows) == [
        AskerCandidate(
            1,
            ReportAskerSource.ASKED_LINE,
            "Mr S. V. Lingam",
            37,
            None,
            None,
            None,
        )
    ]


def test_report_30635_answerer_role_label_inside_a_row_keeps_the_asker() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Dr Ong Chit Chung",
            477,
            "asked the First Deputy Prime Minister what is his assessment of Total Defence.",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Dr Ong Chit Chung",
            477,
            "The Second Minister for Defence (Policy)(Dr Yeo Ning Hong): Mr Speaker, Sir, the concept was introduced in 1984.",
        ),
    ]

    assert [
        asker_candidate.speaker_id
        for asker_candidate in get_asker_candidates(speech_asker_rows)
    ] == [477]


def test_report_45123_withdrawn_question_with_a_note_row_keeps_the_asker() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr Zainal Sapari",
            1127,
            "asked the Minister for Manpower for each year what is the gross monthly income.",
        ),
        _build_row(
            2,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "_Note: Mr Speaker has given his approval for the above question to be withdrawn._",
        ),
    ]

    assert [
        asker_candidate.speaker_id
        for asker_candidate in get_asker_candidates(speech_asker_rows)
    ] == [1127]


def test_report_27802_asker_who_calls_his_own_question_alone_keeps_the_asker() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr J.B. Jeyaretnam",
            638,
            "asked the Minister for Home Affairs if he will inform the House of the provisions of the law",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr J. B. Jeyaretnam (Non-Constituency Member)",
            638,
            "Mr Speaker, Sir, Question 1. But before that is answered, may I say that I have no pecuniary interest",
        ),
    ]

    assert [
        (asker_candidate.printed_name, asker_candidate.speaker_id)
        for asker_candidate in get_asker_candidates(speech_asker_rows)
    ] == [("Mr J.B. Jeyaretnam", 638)]


def test_report_38367_footnote_stood_line_credits_the_filer_who_rises() -> None:
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "Question No. 5* stood in the name of Mr Ong Chang Sam.",
        ),
        _build_row(
            2,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "* Question No. 5 reads as follows:-",
        ),
        _build_row(
            3,
            SpeechKind.DOCUMENT_TEXT,
            None,
            None,
            "To ask the Minister for Finance when will the Rueff Report be presented to this Assembly.",
        ),
        _build_row(4, SpeechKind.SPEECH, "Mr Speaker", 1352, "Mr Ong Chang Sam."),
        _build_row(
            5,
            SpeechKind.SPEECH,
            "Mr Ong Chang Sam (Choa Chu Kang)",
            1383,
            "Mr Speaker, Sir, this House has only just now received a report on the Common Market.",
        ),
        _build_row(
            6,
            SpeechKind.SPEECH,
            "Mr David Marshall",
            1349,
            "asked the Minister for Finance whether he would consider tabling the Rueff Report.",
        ),
    ]

    assert [
        (asker_candidate.source, asker_candidate.printed_name)
        for asker_candidate in get_asker_candidates(speech_asker_rows)
    ] == [
        (ReportAskerSource.STOOD_IN_NAME_LINE, "Mr Ong Chang Sam."),
        (ReportAskerSource.ASKED_LINE, "Mr David Marshall"),
    ]


def test_report_27839_assoc_prof_with_a_dot_and_no_dot_is_read_as_a_name_in_text() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.UNCLASSIFIED,
            None,
            None,
            "1. Assoc. Prof Walter Woon asked the Minister for Information and the Arts what is the rationale",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "The Parliamentary Secretary to the Minister for Information and the Arts (Encik Mohamad Maidin B P M)",
            568,
            "Mr Speaker, Sir, the Singapore Broadcasting Authority (SBA) Internet Content Guidelines help",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Assoc. Prof. Walter Woon (Nominated Member)",
            588,
            "Sir, will the hon. Parliamentary Secretary say who will make the decision?",
        ),
    ]

    assert [
        (asker_candidate.source, asker_candidate.printed_name)
        for asker_candidate in get_asker_candidates(speech_asker_rows)
    ] == [(ReportAskerSource.NAME_IN_TEXT, "Assoc. Prof Walter Woon")]


def test_report_39076_chair_call_with_the_word_question_first_credits_the_member() -> (
    None
):
    speech_asker_rows = [
        _build_row(1, SpeechKind.SPEECH, "Mr Speaker", 1352, "Question. Mr Marshall."),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr David Marshall (Anson)",
            1349,
            "Question No. 1+, Mr Speaker, Sir.",
        ),
        _build_row(
            3,
            SpeechKind.EDITORIAL_NOTE,
            None,
            None,
            "+ The Question reads as follows:-",
        ),
        _build_row(
            4,
            SpeechKind.EDITORIAL_NOTE,
            None,
            None,
            "To ask the Prime Minister whether the statement made by him over Radio Singapore",
        ),
        _build_row(
            5,
            SpeechKind.SPEECH,
            "The Prime Minister (Mr Lee Kuan Yew)",
            30,
            "not being in his seat -",
        ),
    ]

    assert get_asker_candidates(speech_asker_rows) == [
        AskerCandidate(
            row_ordinal=1,
            source=ReportAskerSource.CHAIR_CALL,
            printed_name="Mr Marshall",
            speaker_id=1349,
            reader_printed_name=None,
            reader_speaker_id=None,
            reader_row_ordinal=None,
        )
    ]


def test_report_38885_chair_call_with_the_question_number_credits_the_member() -> None:
    speech_asker_rows = [
        _build_row(
            1, SpeechKind.SPEECH, "Mr Speaker", 1352, "Mr Marshall, Question No. 22."
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr David Marshall",
            1349,
            "Sir, the Government Gazette of yesterday's date has answered my question*.",
        ),
        _build_row(
            3,
            SpeechKind.EDITORIAL_NOTE,
            None,
            None,
            "*The question reads as follows:",
        ),
        _build_row(
            4,
            SpeechKind.EDITORIAL_NOTE,
            None,
            None,
            "To ask the Minister for Education when will the Commission be appointed.",
        ),
    ]

    assert [
        (
            asker_candidate.source,
            asker_candidate.printed_name,
            asker_candidate.speaker_id,
        )
        for asker_candidate in get_asker_candidates(speech_asker_rows)
    ] == [(ReportAskerSource.CHAIR_CALL, "Mr Marshall", 1349)]


def test_chair_call_is_ignored_when_another_member_row_follows_it() -> None:
    speech_asker_rows = [
        _build_row(
            1, SpeechKind.SPEECH, "Mr Speaker", 1352, "Mr Marshall, Question No. 22."
        ),
        _build_row(
            2, SpeechKind.SPEECH, "Mr Lim Kim San", 64, "Sir, the answer is no."
        ),
    ]

    assert get_asker_candidates(speech_asker_rows) == []


def test_chair_call_is_ignored_when_the_report_has_another_asker() -> None:
    speech_asker_rows = [
        _build_row(
            1, SpeechKind.SPEECH, "Mr Speaker", 1352, "Mr Marshall, Question No. 22."
        ),
        _build_row(2, SpeechKind.SPEECH, "Mr David Marshall", 1349, "Sir, I rise."),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr Ong Chang Sam",
            1383,
            "asked the Minister for Finance what progress has been made.",
        ),
    ]

    assert [
        asker_candidate.source
        for asker_candidate in get_asker_candidates(speech_asker_rows)
    ] == [ReportAskerSource.ASKED_LINE]


def test_report_35665_my_question_is_after_leave_for_a_question_without_notice() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr Speaker",
            192,
            "The hon. Member for Serangoon Gardens wishes to ask a question without notice, as provided for under Standing Order No. 19. I have therefore given him permission to ask the question.",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr L. P. Rodrigo (Serangoon Gardens)",
            174,
            "Mr Speaker, Sir, today we all know of the tragic fire which broke out at the Robinson departmental store.",
        ),
        _build_row(
            3,
            SpeechKind.SPEECH,
            "Mr L. P. Rodrigo (Serangoon Gardens)",
            174,
            "My question is simply to ask the Minister for Social Affairs if he would inform this House of the tragic outcome of the fire.",
        ),
        _build_row(
            4,
            SpeechKind.SPEECH,
            "The Minister for Social Affairs (Encik Othman Bin Wok)",
            169,
            "Mr Speaker, Sir, at 1006 hours yesterday, the Fire Brigade Control Room received a telephone call.",
        ),
    ]

    assert [
        (
            asker_candidate.source,
            asker_candidate.row_ordinal,
            asker_candidate.speaker_id,
        )
        for asker_candidate in get_asker_candidates(speech_asker_rows)
    ] == [(ReportAskerSource.ASKED_LINE, 3, 174)]


def test_my_question_is_without_leave_for_a_question_without_notice_credits_no_one() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Mr Speaker",
            192,
            "Order. The Member may proceed.",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Mr L. P. Rodrigo (Serangoon Gardens)",
            174,
            "My question is simply to ask the Minister for Social Affairs if he would inform this House.",
        ),
    ]

    assert get_asker_candidates(speech_asker_rows) == []


def test_to_ask_block_read_out_has_no_filer_when_the_chair_calls_no_one_of_the_block() -> (
    None
):
    speech_asker_rows = [
        _build_row(
            1,
            SpeechKind.SPEECH,
            "Dr Aline K. Wong",
            415,
            "To ask the Acting Minister for Health (a) what is the type of Hepatitis B vaccine.",
        ),
        _build_row(
            2,
            SpeechKind.SPEECH,
            "Dr Ho Tat Kin",
            370,
            "To ask the Acting Minister for Health, in view of the worldwide concern over Aids.",
        ),
        _build_row(3, SpeechKind.SPEECH, "Mr Deputy Speaker", 403, "Dr Tan."),
        _build_row(
            4, SpeechKind.SPEECH, "Mr Chew Heng Ching", 358, "Question No. 20, Sir."
        ),
    ]

    assert [
        asker_candidate.reader_printed_name
        for asker_candidate in get_asker_candidates(speech_asker_rows)
    ] == [None, None]
