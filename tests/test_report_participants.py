from dataclasses import dataclass, replace
from typing import Optional

import pytest

from crud.speech import SpeechAskerRow
from database.report_participant import ReportParticipant
from database.report_question_state import ReportQuestionState
from enums import (
    OfficeClass,
    OfficeSource,
    ParticipantRole,
    ParticipantRoleSource,
    QuestionState,
    ReportAskerSource,
    SpeechKind,
)
from services.report_asker import get_asker_candidates, get_question_row_ordinals
from services.report_participant import (
    build_report_participants,
    build_report_question_states,
    get_not_a_question_state,
    get_participants,
    get_question_states,
    read_inline_speakers,
    read_nested_label_speakers,
)
from utils.asker_candidate import AskerCandidate
from utils.office import Office

_REPORT_ID = 1
_ROW_COLUMN_SEPARATOR = " | "
_DESMOND_LEE_SPEAKER_ID = 1039
_HENG_CHEE_HOW_SPEAKER_ID = 826
_SIM_ANN_SPEAKER_ID = 990
_VASOO_SPEAKER_ID = 411
_CHARLES_CHONG_SPEAKER_ID = 619
_TEO_CHONG_TEE_SPEAKER_ID = 338
_JOHN_CHEN_SPEAKER_ID = 612


@dataclass(frozen=True)
class _LabelledReport:
    participants: list[ReportParticipant]
    states: list[ReportQuestionState]


def _parse_rows(rows_text: str) -> list[SpeechAskerRow]:
    speech_asker_rows: list[SpeechAskerRow] = []
    for line in rows_text.strip().splitlines():
        ordinal, kind, speaker_id, speaker, transcript = line.split(
            _ROW_COLUMN_SEPARATOR, maxsplit=4
        )
        speech_asker_rows.append(
            SpeechAskerRow(
                id=int(ordinal),
                report_id=_REPORT_ID,
                ordinal=int(ordinal),
                speaker=speaker or None,
                transcript=transcript,
                kind=SpeechKind(kind) if kind else None,
                speaker_id=int(speaker_id) if speaker_id else None,
            )
        )
    return speech_asker_rows


def _resolve_asker_candidates(
    asker_candidates: list[AskerCandidate],
    printed_name_to_speaker_id: dict[str, int],
) -> list[AskerCandidate]:
    return [
        replace(
            asker_candidate,
            speaker_id=printed_name_to_speaker_id.get(
                asker_candidate.printed_name, asker_candidate.speaker_id
            ),
        )
        for asker_candidate in asker_candidates
    ]


def _label_report(
    title: str,
    rows_text: str,
    printed_name_to_speaker_id: Optional[dict[str, int]] = None,
    speaker_id_to_office: Optional[dict[int, Office]] = None,
    inline_label_to_speaker_id: Optional[dict[str, int]] = None,
) -> _LabelledReport:
    speech_asker_rows = _parse_rows(rows_text)
    asker_candidates = _resolve_asker_candidates(
        get_asker_candidates(speech_asker_rows), printed_name_to_speaker_id or {}
    )
    question_row_ordinals = get_question_row_ordinals(speech_asker_rows)
    not_a_question_state = get_not_a_question_state(
        title, speech_asker_rows, asker_candidates, question_row_ordinals
    )
    if not_a_question_state is not None:
        return _LabelledReport(
            [], build_report_question_states(_REPORT_ID, [not_a_question_state])
        )
    participant_candidates = get_participants(
        title,
        read_inline_speakers(
            read_nested_label_speakers(
                speech_asker_rows, (inline_label_to_speaker_id or {}).get
            ),
            (inline_label_to_speaker_id or {}).get,
        ),
        asker_candidates,
        question_row_ordinals,
        speaker_id_to_office or {},
    )
    question_state_candidates = get_question_states(
        title, speech_asker_rows, participant_candidates
    )
    return _LabelledReport(
        build_report_participants(_REPORT_ID, participant_candidates),
        build_report_question_states(_REPORT_ID, question_state_candidates),
    )


def _summarise_participants(
    report_participants: list[ReportParticipant],
) -> list[tuple[ParticipantRole, ParticipantRoleSource, int, str, Optional[int]]]:
    return [
        (
            report_participant.role,
            report_participant.role_source,
            report_participant.first_ordinal,
            report_participant.printed_name,
            report_participant.speaker_id,
        )
        for report_participant in report_participants
    ]


def _summarise_office_marks(
    report_participants: list[ReportParticipant],
) -> list[
    tuple[
        ParticipantRole,
        Optional[int],
        Optional[str],
        Optional[str],
        Optional[OfficeClass],
        Optional[OfficeSource],
    ]
]:
    return [
        (
            report_participant.role,
            report_participant.speaker_id,
            report_participant.answering_for_printed,
            report_participant.office_printed,
            report_participant.office_class,
            report_participant.office_source,
        )
        for report_participant in report_participants
        if report_participant.answering_for_printed is not None
        or report_participant.office_printed is not None
    ]


def _summarise_states(
    report_question_states: list[ReportQuestionState],
) -> list[tuple[QuestionState, str, Optional[int]]]:
    return [
        (
            report_question_state.state,
            report_question_state.printed_text,
            report_question_state.first_ordinal,
        )
        for report_question_state in report_question_states
    ]


_REPORT_11789_TITLE = "Tougher Stance on Drug Traffickers and Syndicates"
_REPORT_11789_ROWS = """
1 | PROCEDURAL |  |  | The following question stood in the name of Mr Christopher de Souza –
2 | SPEECH | 1033 | Mr Christopher de Souza | 9 To ask the Minister for Home Affairs whether there is an upward trend of drug syndicates
3 | SPEECH | 1033 | Mr Christopher de Souza | asked the Minister for Home Affairs (a) what is the Ministry’s position on the research paper
4 | SPEECH | 1111 | Mr Speaker | Can someone ask the Question on his behalf?
5 | SPEECH | 1043 | Mr Cedric Foo Chee Keng (Pioneer) | Question No 9.
6 | SPEECH | 1109 | The Senior Parliamentary Secretary to the Minister for Home Affairs (Ms Sun Xueling) (for the Minister for Home Affairs) | Mr Speaker, with your permission, may I take Question Nos 9 and 10 together?
7 | SPEECH | 1111 | Mr Speaker | Yes, please.
8 | SPEECH | 1109 | Ms Sun Xueling | Drugs destroy lives and impose immense costs on individuals and society. Besides tangible costs,
9 | SPEECH | 1109 | Ms Sun Xueling | The research paper attempted to quantify the costs to Singapore of drug crime, both tangible and
10 | SPEECH | 1109 | Ms Sun Xueling | The high costs drugs impose on society is one reason why we must maintain our firm stance against
11 | SPEECH | 1109 | Ms Sun Xueling | CNB has not yet detected any trend of drug syndicates deliberately targeting young persons, be it
12 | SPEECH | 1109 | Ms Sun Xueling | Nevertheless, we take this risk very seriously. We have strengthened our legislative framework and
13 | SPEECH | 1109 | Ms Sun Xueling | In 2012, the Misuse of Drugs Act (MDA) was amended to provide for an offence for any adult who
14 | SPEECH | 1109 | Ms Sun Xueling | In 2019, MDA was further amended to provide more protection to children below 16 years of age and
15 | SPEECH | 1111 | Mr Speaker | Mr Christopher de Souza.
16 | SPEECH | 1033 | Mr Christopher de Souza (Holland-Bukit Timah) | I thank the Senior Parliamentary Secretary for the response. The question is, in light of the
17 | SPEECH | 1109 | Ms Sun Xueling | I thank the Member for his questions. Indeed, the push for drug legalisation around the world is a
18 | SPEECH | 1109 | Ms Sun Xueling | We have now undertaken this study. We hope to add to the literature so that more are aware about
19 | SPEECH | 1109 | Ms Sun Xueling | At the same time, we are also stepping up our education outreach. We understand that preventive
20 | SPEECH | 1109 | Ms Sun Xueling | At the end of the day, what we are going to do is going to be guided by research. At the same time,
"""
_REPORT_18268_TITLE = "Source Countries for Construction Workers"
_REPORT_18268_ROWS = """
1 | PROCEDURAL |  |  | The following questions stood in the name of Mr R Dhinakaran –
2 | SPEECH | 987 | Mr R Dhinakaran | 3 To ask the Acting Minister for Manpower (a) whether Filipino and Sri Lankan construction workers
3 | SPEECH | 987 | Mr R Dhinakaran | 4 To ask the Acting Minister for Manpower in light of better-skilled Filipino construction workers
4 | SPEECH | 984 | Mr Patrick Tay Teck Guan (Nee Soon) | Question No 3, Madam.
5 | SPEECH | 995 | The Acting Minister for Manpower (Mr Tan Chuan-Jin) | Mdm Speaker, last year, BCA appointed Singapore-based companies to set up Overseas Testing Centres
6 | SPEECH | 995 | The Acting Minister for Manpower (Mr Tan Chuan-Jin) | We are, indeed, making a deliberate move to opt for quality over cost. We are achieving this in
7 | SPEECH | 995 | The Acting Minister for Manpower (Mr Tan Chuan-Jin) | MOM and MND/BCA will also be consulting the industry to explore having a minimum percentage of R1
8 | SPEECH | 934 | Mdm Speaker | Mr Dhinakaran, Question No 4.
9 | SPEECH | 987 | Mr R Dhinakaran (Nominated Member) | Question No 4, Mdm Speaker.
10 | SPEECH | 995 | Mr Tan Chuan-Jin | My apologies, Mdm Speaker, in my prior answer, if I could have retrospectively requested your
11 | SPEECH | 934 | Mdm Speaker | Okay. The two questions were combined. Mr Dhinakaran.
12 | SPEECH | 987 | Mr R Dhinakaran | Thank you, Madam. I thank the Acting Minister for the explanation. I wish to ask a supplementary
13 | SPEECH | 987 | Mr R Dhinakaran | Another question is: in this Budget, Deputy Prime Minister mentioned the other day that the maximum
14 | SPEECH | 995 | Mr Tan Chuan-Jin | Mdm Speaker, we are not particularly reducing the supply of workers from some of these existing
"""
_REPORT_45746_TITLE = "Impact of Local Qualifying Salary Requirement and Expansion of Progressive Wage Model on Costs, Productivity and Jobs"
_REPORT_45746_ROWS = """
1 | SPEECH | 1216 | Mr Sharael Taha | asked the Minister for Manpower (a) how does the Ministry
2 | SPEECH | 1164 | Ms He Ting Ru | asked the Minister for Manpower (a) for each of the last
3 | SPEECH | 1208 | Miss Rachel Ong | asked the Minister for Manpower (a) how will employers be
4 | SPEECH | 1208 | Miss Rachel Ong | asked the Minister for Manpower (a) what are the
5 | SPEECH | 1172 | Ms Jessica Tan Soon Neo | asked the Minister for Manpower in light of the expanding
6 | SPEECH | 1172 | Ms Jessica Tan Soon Neo | asked the Minister for Manpower in light of the expanding
7 | SPEECH | 1205 | Ms Hazel Poa | asked the Minister for Manpower how many Singaporean
8 | SPEECH | 1153 | Mr Edward Chia Bing Hui | asked the Minister for Manpower how does the Ministry
9 | SPEECH | 1142 | Miss Cheng Li Hui | asked the Minister for Manpower with the proposed increase
10 | SPEECH | 1183 | Mr Liang Eng Hwa | asked the Minister for Manpower (a) what transitory support
11 | SPEECH | 1153 | Mr Edward Chia Bing Hui | asked the Minister for Manpower (a) how is the Local
12 | SPEECH | 1153 | Mr Edward Chia Bing Hui | asked the Minister for Manpower (a) how does the Ministry
13 | SPEECH | 1150 | Mr Desmond Choo | asked the Minister for Manpower in light of the tightened
14 | SPEECH | 1198 | Ms Ng Ling Ling | asked the Minister for Manpower in view of increases in
15 | SPEECH | 1239 | The Senior Minister of State for Manpower (Mr Zaqy Mohamad) (for the Minister of Manpower) | Mr Speaker, with your permission, I would like to take
16 | SPEECH | 1223 | Mr Speaker | Please do.
17 | SPEECH | 1239 | Mr Zaqy Mohamad | I thank Members for their interest in the recent
18 | SPEECH | 1239 | Mr Zaqy Mohamad | The Workgroup's vision is for a strengthened social compact
19 | SPEECH | 1239 | Mr Zaqy Mohamad | Uplifting lower-wage workers has been a priority for the
20 | SPEECH | 1239 | Mr Zaqy Mohamad | Mr Speaker, building on the foundation of Workfare, the
21 | SPEECH | 1239 | Mr Zaqy Mohamad | Over the last decade, our policies to support lower-wage
22 | SPEECH | 1239 | Mr Zaqy Mohamad | Low-income households would, therefore, benefit from our
23 | SPEECH | 1239 | Mr Zaqy Mohamad | The Workgroup achieved tripartite consensus on 18
24 | SPEECH | 1239 | Mr Zaqy Mohamad | First, we will expand Progressive Wages to new sectors like
25 | SPEECH | 1239 | Mr Zaqy Mohamad | Second, we will introduce a new Local Qualifying Salary
26 | SPEECH | 1239 | Mr Zaqy Mohamad | Third, we will introduce the Progressive Wage Mark, or PW
27 | SPEECH | 1239 | Mr Zaqy Mohamad | The Workgroup has not deviated from the broad principle
28 | SPEECH | 1239 | Mr Zaqy Mohamad | Mr Edward Chia and Mr Sharael Taha asked about the
29 | SPEECH | 1239 | Mr Zaqy Mohamad | These will be done by sectoral Tripartite Clusters for the
30 | SPEECH | 1239 | Mr Zaqy Mohamad | Tripartism is our strength, and some say our secret sauce,
31 | SPEECH | 1239 | Mr Zaqy Mohamad | If wage growth of our lower-wage workers outpace
32 | SPEECH | 1239 | Mr Zaqy Mohamad | For many years, firms hiring foreign workers have been
33 | SPEECH | 1239 | Mr Zaqy Mohamad | To Ms He Ting Ru’s query, there are 103,000 full-time
34 | SPEECH | 1239 | Mr Zaqy Mohamad | With the new LQS requirement, an estimated 77% of these
35 | SPEECH | 1239 | Mr Zaqy Mohamad | To Ms Hazel Poa’s query, the remaining 23%, who are not
36 | SPEECH | 1239 | Mr Zaqy Mohamad | While not formally covered by the LQS requirement, these
37 | SPEECH | 1239 | Mr Zaqy Mohamad | Some Members, including Mr Yip Hon Weng, asked about how
38 | SPEECH | 1239 | Mr Zaqy Mohamad | We recognise that the new LQS requirement in 2022 will have
39 | SPEECH | 1239 | Mr Zaqy Mohamad | I urge Members not to look at each measure in isolation but
40 | SPEECH | 1239 | Mr Zaqy Mohamad | Members have also asked about the implementation details. I
41 | SPEECH | 1239 | Mr Zaqy Mohamad | To Mr Edward Chia’s query, firms that hire foreign workers
42 | SPEECH | 1239 | Mr Zaqy Mohamad | In designing the system to support the new moves, we will
43 | SPEECH | 1239 | Mr Zaqy Mohamad | Employers will also be able to refer to MOM’s website to
44 | SPEECH | 1239 | Mr Zaqy Mohamad | To Mr Liang Eng Hwa’s query on how the PW Mark will be
45 | SPEECH | 1239 | Mr Zaqy Mohamad | Mr Speaker, Sir, uplifting lower-wage workers is a
46 | SPEECH | 1239 | Mr Zaqy Mohamad | The Government will do its part, too. With respect to
47 | SPEECH | 1239 | Mr Zaqy Mohamad | With respect to workers, I have already touched on the
48 | SPEECH | 1239 | Mr Zaqy Mohamad | Miss Rachel Ong asked why we are lowering the Workfare
49 | SPEECH | 1239 | Mr Zaqy Mohamad | For workers aged 30 to 34, however, some continued to
50 | SPEECH | 1239 | Mr Zaqy Mohamad | Miss Cheng Li Hui and other Members asked if businesses
51 | SPEECH | 1239 | Mr Zaqy Mohamad | I, therefore, hope that Singaporeans will not accuse firms
52 | SPEECH | 1239 | Mr Zaqy Mohamad | Because the growth of Progressive Wages is negotiated
53 | SPEECH | 1239 | Mr Zaqy Mohamad | Mr Speaker, Sir, the effort to uplift our lower-wage
54 | SPEECH | 1239 | Mr Zaqy Mohamad | The Government has committed to providing transitional
55 | SPEECH | 1223 | Mr Speaker | Ms Jessica Tan.
56 | SPEECH | 1172 | Ms Jessica Tan Soon Neo (East Coast) | Thank you, Mr Speaker. I thank the Senior Minister of State
57 | SPEECH | 1239 | Mr Zaqy Mohamad | I thank the Member for her question. In fact, as I have
58 | SPEECH | 1239 | Mr Zaqy Mohamad | Speaking to employers, I know some are also concerned that
59 | SPEECH | 1239 | Mr Zaqy Mohamad | On LQS, this is a measure that most employers are already
60 | SPEECH | 1239 | Mr Zaqy Mohamad | So, look forward to some of the upcoming PWMs – food
61 | SPEECH | 1239 | Mr Zaqy Mohamad | So, looking at all these wage benchmarks and wage ladders
62 | SPEECH | 1223 | Mr Speaker | Ms Hazel Poa.
63 | SPEECH | 1205 | Ms Hazel Poa (Non-Constituency Member) | I thank the Senior Minister of State for his reply. I would
64 | SPEECH | 1205 | Ms Hazel Poa (Non-Constituency Member) | Firstly, would employers who wish to employ foreigners no
65 | SPEECH | 1205 | Ms Hazel Poa (Non-Constituency Member) | Last question: the Senior Minister of State mentioned that
66 | SPEECH | 1239 | Mr Zaqy Mohamad | I thank Ms Hazel Poa for her query. In fact, in response, I
67 | SPEECH | 1239 | Mr Zaqy Mohamad | Also, bear in mind that the remainder that is left are
68 | SPEECH | 1239 | Mr Zaqy Mohamad | On the Member's second question on part-timers, if you look
69 | SPEECH | 1223 | Mr Speaker | Mr Edward Chia.
70 | SPEECH | 1153 | Mr Edward Chia Bing Hui (Holland-Bukit Timah) | Mr Speaker, I would like to ask the Senior Minister of
71 | SPEECH | 1239 | Mr Zaqy Mohamad | I thank Mr Chia for his questions.
72 | SPEECH | 1239 | Mr Zaqy Mohamad | Two things: one, let me just start with the LQS. I think I
73 | SPEECH | 1239 | Mr Zaqy Mohamad | It will be a light touch up front. But I am quite sure
74 | SPEECH | 1239 | Mr Zaqy Mohamad | On the second question on firm level productivity and
75 | SPEECH | 1239 | Mr Zaqy Mohamad | I will give an example. Like the securities sector, for
76 | SPEECH | 1239 | Mr Zaqy Mohamad | I think if you look at many other sectors, including
77 | SPEECH | 1239 | Mr Zaqy Mohamad | These are ways in which they can offer more, use better
78 | SPEECH | 1239 | Mr Zaqy Mohamad | This is one way in which when you look at productivity
79 | SPEECH | 1172 | Mdm Deputy Speaker | Mr Gerald Giam.
80 | SPEECH | 1160 | Mr Gerald Giam Yean Song (Aljunied) | Madam, I have one supplementary question. The LQS was not
81 | SPEECH | 1239 | Mr Zaqy Mohamad | To answer the Member's question, maybe it is by coincidence
82 | SPEECH | 1239 | Mr Zaqy Mohamad | The main goal of the LQS was also to ensure that
83 | SPEECH | 1239 | Mr Zaqy Mohamad | Unlike minimum wage laws around the world, there is the
84 | SPEECH | 1239 | Mr Zaqy Mohamad | This enables us to make a differentiation, but the overall
85 | SPEECH | 1239 | Mr Zaqy Mohamad | On balance, maybe, perhaps, it is coincidental, but the
86 | SPEECH | 1239 | Mr Zaqy Mohamad | We also have to manage over time and that is why we also
87 | SPEECH | 1239 | Mr Zaqy Mohamad | These are quite complex matters which we need to give
88 | SPEECH | 1172 | Mdm Deputy Speaker | Mr Yip Hon Weng.
89 | SPEECH | 1238 | Mr Yip Hon Weng (Yio Chu Kang) | Thank you, Mdm Deputy Speaker. I thank the Senior Minister
90 | SPEECH | 1239 | Mr Zaqy Mohamad | I thank the Member for the question. The short answer is
91 | SPEECH | 1239 | Mr Zaqy Mohamad | But overall, that is why it is also important for our PWMs
92 | SPEECH | 1172 | Mdm Deputy Speaker | Mr Leon Perera.
"""
_REPORT_6147_TITLE = "Review of Salary and Benefits for Educators and Staff in Mainstream Schools, Preschools and Special Education Schools"
_REPORT_6147_ROWS = """
1 | SPEECH | 1148 | Ms Denise Phua Lay Peng | asked the Minister for Education when and how are salary scale and benefit reviews conducted and
2 | SPEECH | 1137 | The Minister for Education (Mr Chan Chun Sing) | Mr Deputy Speaker, Sir, MOE periodically reviews the salaries of officers in MOE schemes of service
3 | SPEECH | 1137 | The Minister for Education (Mr Chan Chun Sing) | Salary adjustments take into consideration the size of the salary gaps compared to market
4 | SPEECH | 1137 | The Minister for Education (Mr Chan Chun Sing) | MOE recently announced salary adjustments for all eligible Education Officers (EOs), Allied
5 | SPEECH | 1137 | The Minister for Education (Mr Chan Chun Sing) | ECDA is separately conducting a salary review for Early Childhood educators in government-supported
6 | SPEECH | 1137 | The Minister for Education (Mr Chan Chun Sing) | Special Education (SPED) schools are run by Social Service Agencies (SSAs). While SPED schools
7 | SPEECH | 1137 | The Minister for Education (Mr Chan Chun Sing) | Nevertheless, MOE, in our role in overseeing the SPED sector, works closely with and supports the
8 | SPEECH | 1137 | The Minister for Education (Mr Chan Chun Sing) | For non-teaching SPED school staff such as psychologists, the SSAs take reference from the NCSS
9 | SPEECH | 1144 | Mr Deputy Speaker | Ms Denise Phua.
10 | SPEECH | 1148 | Ms Denise Phua Lay Peng (Jalan Besar) | I thank the Minister for his comprehensive reply. Let me declare that I am a volunteer at several
11 | SPEECH | 1148 | Ms Denise Phua Lay Peng (Jalan Besar) | Recently, when the announcement for MOE teachers or Education Officers was made, it created quite a
12 | SPEECH | 1148 | Ms Denise Phua Lay Peng (Jalan Besar) | I think it is always good and would MOE consider that when it makes announcements of such nature,
13 | SPEECH | 1148 | Ms Denise Phua Lay Peng (Jalan Besar) | Number two, I would like MOE to consider and communicate to the SSAs – either special schools or
14 | SPEECH | 1137 | Mr Chan Chun Sing | Mr Deputy Speaker, Sir, to the first comment by Ms Denise Phua, yes, indeed, Public Service
15 | SPEECH | 1137 | Mr Chan Chun Sing | On the second comment, we will continue to share our methodologies of how this is done in the
16 | SPEECH | 1144 | Mr Deputy Speaker | Mr Leong Mun Wai.
17 | SPEECH | 1182 | Mr Leong Mun Wai (Non-Constituency Member) | Thank you, Sir. It is important that in every sector in the economy, we must allocate some of our
18 | SPEECH | 1182 | Mr Leong Mun Wai (Non-Constituency Member) | Secondly, in the long run, we must also ensure that every sector has a fair salary structure. For
19 | SPEECH | 1144 | Mr Deputy Speaker | Sorry, Mr Leong Mun Wai, are you asking a question or are you —
20 | SPEECH | 1182 | Mr Leong Mun Wai | Sir, I am asking the question whether there are plans in the future that will ensure that these
21 | SPEECH | 1144 | Mr Christopher de Souza | Minister Chan Chun Sing.
22 | SPEECH | 1137 | Mr Chan Chun Sing | Mr Deputy Speaker, Sir, to Mr Leong's first comment, yes, indeed, first of all, we try to get a
23 | SPEECH | 1137 | Mr Chan Chun Sing | Specific to Mr Leong Mun Wai's question, Mr Leong might want to know or may already know that
24 | SPEECH | 1137 | Mr Chan Chun Sing | On Mr Leong Mun Wai's second point about the salary structure, indeed, that is also what we have
25 | SPEECH | 1137 | Mr Chan Chun Sing | But I would just like to raise one nuanced point. I think we should be very careful about
26 | SPEECH | 1137 | Mr Chan Chun Sing | We look at it holistically. We look at some of the prior training that our people have, the
"""
_REPORT_6095_TITLE = (
    "Cryptocurrency-related Scams Reported Annually in Past Three Years"
)
_REPORT_6095_ROWS = """
1 | SPEECH | 1190 | Mr Melvin Yong Yik Chye | asked the Minister for Home Affairs (a) how many scams related to cryptocurrency have been reported
2 | SPEECH | 1175 | Mr K Shanmugam | In 2019, the Police received 125 reports related to cryptocurrency scams. This increased to 397 in
3 | SPEECH | 1175 | Mr K Shanmugam | The vast majority of cryptocurrency scams are perpetrated by scammers based outside Singapore. As
4 | SPEECH | 1175 | Mr K Shanmugam | Nonetheless, we have stepped up our investigation efforts. The Police established a cryptocurrency
5 | SPEECH | 1175 | Mr K Shanmugam | The best defence, however, is a discerning public. To that end, we have stepped up public education
6 | SPEECH | 1175 | Mr K Shanmugam | Members of the public should practise healthy scepticism to ask, check and confirm, before making
"""
_REPORT_19273_TITLE = "Cost of Conducting the Recent Punggol East By-election"
_REPORT_19273_ROWS = """
1 | SPEECH | 996 | Asst Prof Tan Kheng Boon Eugene | asked the Prime Minister what is the cost of conducting the Punggol East by-election in January
2 | SPEECH | 1001 | Mr Teo Chee Hean (for the Prime Minister) | The expenditure incurred by the Elections Department for the Punggol East By-Election in January
"""
_REPORT_11034_TITLE = "Updates on Matters Arising from High Court Judgment in Former Foreign Domestic Worker Parti Liyani's Case"
_REPORT_11034_ROWS = """
1 | SPEECH | 1195 | Mr Murali Pillai | asked the Minister for Home Affairs following the judgment of the High Court in _Parti Liyani v PP
2 | SPEECH | 1224 | Dr Tan Wu Meng | asked the Minister for Home Affairs in respect of the High Court judgment in _Parti Liyani v PP
3 | SPEECH | 1224 | Dr Tan Wu Meng | asked the Minister for Home Affairs over the last five years (a) what percentage of cases of theft
4 | SPEECH | 1232 | Mr Vikram Nair | asked the Minister for Home Affairs whether there are any updates on its internal reviews of what
5 | SPEECH | 1182 | Mr Leong Mun Wai | asked the Minister for Home Affairs whether he will appoint a committee of inquiry consisting of
6 | SPEECH | 1199 | Mr Louis Ng Kok Kwang | asked the Minister for Home Affairs whether the Ministry will consider allowing foreign domestic
7 | SPEECH | 1183 | Mr Liang Eng Hwa | asked the Minister for Home Affairs what has gone wrong in the chain of events related to the case
8 | SPEECH | 1161 | Mr Derrick Goh | asked the Minister for Home Affairs what are the root causes that led to the procedural lapses on
9 | SPEECH | 1232 | Mr Vikram Nair | asked the Minister for Law whether there are any updates on the Ministry's internal reviews of what
10 | SPEECH | 1182 | Mr Leong Mun Wai | asked the Minister for Law in light of the Parti Liyani case (a) whether an expedited trial process
11 | SPEECH | 1240 | Mr Zhulkarnain Abdul Rahim | asked the Minister for Law whether the Government will consider providing direct legal aid to
12 | SPEECH | 1184 | Mr Lim Biow Chuan | asked the Minister for Law how many State Court judges have previously worked as prosecutors in the
13 | SPEECH | 1161 | Mr Derrick Goh | asked the Minister for Law with regard to the case of _Parti Liyani v PP [2020] SGHC 187_ where
14 | SPEECH | 1152 | The Minister of State for Home Affairs (Mr Desmond Tan) (on behalf of the Minister for Home Affairs and Law) | Mr Speaker, may I seek your permission to take Question Nos 4 to 11, on behalf of the Minister for
15 | SPEECH | 1223 | Mr Speaker | Please proceed.
16 | SPEECH | 1152 | Mr Desmond Tan | The agencies have considered the High Court judgment and are conducting reviews. These reviews are
17 | SPEECH | 1195 | Mr Murali Pillai (Bukit Batok) | If I may, Sir, I would like to ask the hon Minister of State, in relation to the scope of the
18 | SPEECH | 1223 | Mr Speaker | Can you keep the supplementary questions in two, as I had mentioned at the last sitting?
19 | SPEECH | 1195 | Mr Murali Pillai | Yes, Sir. In relation to the issue about the disciplinary proceedings that has been commenced by Ms
20 | SPEECH | 1223 | Mr Speaker | Minister Shanmugam.
21 | SPEECH | 1175 | The Minister for Home Affairs and Minister for Law (Mr K Shanmugam) | Sir, as regard to the questions and whether we will cover them, I will hope to cover the questions
22 | SPEECH | 1175 | The Minister for Home Affairs and Minister for Law (Mr K Shanmugam) | On the disciplinary proceedings, no decision has been made by the Court, and I prefer to wait until
23 | SPEECH | 1182 | Mr Leong Mun Wai (Non-Constituency Member) | Mr Speaker, I would like to ask the Minister for Home Affairs that given the errors which have
24 | SPEECH | 1175 | Mr K Shanmugam | Sir, as I have indicated, let me finish the reviews, deal with that, present an account in
25 | SPEECH | 1182 | Mr Leong Mun Wai | Thank you, Minister.
26 | SPEECH | 1223 | Mr Speaker | Ms Yeo Wan Ling.
"""
_REPORT_44970_TITLE = "Enhancing Measures to Prevent Sexual Harassment in Schools and Institutes of Higher Learning"
_REPORT_44970_ROWS = """
1 | SPEECH | 1121 | Ms Tin Pei Ling | asked the Minister for Education what measures are in place
2 | SPEECH | 1045 | Ms Foo Mee Har | asked the Minister for Education what safeguards and
3 | SPEECH | 1088 | Mr Muhamad Faisal Bin Abdul Manap | asked the Minister for Education (a) what measures were put
4 | SPEECH | 1088 | Mr Muhamad Faisal Bin Abdul Manap | asked the Minister for Education (a) what are the forms of
5 | SPEECH | 1056 | The Second Minister for Education (Ms Indranee Rajah) (for the Minister for Education) | Mr Speaker, with your permission, may I take Question Nos 4
6 | SPEECH | 1111 | Mr Speaker | Yes, please.
7 | SPEECH | 1056 | Ms Indranee Rajah | Minister Ong Ye Kung addressed questions relating to the
8 | SPEECH | 1056 | Ms Indranee Rajah | Ms Tin Pei Ling asked about the prevention of sexual
9 | SPEECH | 1056 | Ms Indranee Rajah | Beyond disciplinary measures, students are taught to
10 | SPEECH | 1056 | Ms Indranee Rajah | The other areas of concern raised by Ms Foo Mee Har, Mr
11 | SPEECH | 1056 | Ms Indranee Rajah | In terms of support, the first and most fundamental thing
12 | SPEECH | 1056 | Ms Indranee Rajah | The recent case reported by National University of
13 | SPEECH | 1056 | Ms Indranee Rajah | The other IHLs are similarly concerned and are in the
14 | SPEECH | 1056 | Ms Indranee Rajah | As the IHLs do their reviews, there are three broad areas
15 | SPEECH | 1056 | Ms Indranee Rajah | First, support for victims. All the IHLs have full-time
16 | SPEECH | 1056 | Ms Indranee Rajah | Our IHLs will look to strengthening these provisions,
17 | SPEECH | 1056 | Ms Indranee Rajah | A good support system must create psychological safety for
18 | SPEECH | 1056 | Ms Indranee Rajah | We also need to recognise that individuals have different
19 | SPEECH | 1056 | Ms Indranee Rajah | Second, campus security to deter would-be offenders.
20 | SPEECH | 1056 | Ms Indranee Rajah | More will be done. Over this past week, NUS started
21 | SPEECH | 1056 | Ms Indranee Rajah | NUS expects to complete these enhancements in the coming
22 | SPEECH | 1056 | Ms Indranee Rajah | Third, ensuring a collective stand against sexual
23 | SPEECH | 1056 | Ms Indranee Rajah | At its core, the issue is about respect for others. There
24 | SPEECH | 1056 | Ms Indranee Rajah | We can and, therefore, must do better to educate students
25 | SPEECH | 1056 | Ms Indranee Rajah | Technology has also amplified the potential for harm
26 | SPEECH | 1056 | Ms Indranee Rajah | Institutions and organisations must also recognise that
27 | SPEECH | 1056 | Ms Indranee Rajah | At the end of the day, the best deterrent and protection in
28 | SPEECH | 1111 | Mr Speaker | Er Dr Lee Bee Wah.
29 | SPEECH | 1072 | Er Dr Lee Bee Wah (Nee Soon) | Mr Speaker, Sir, I have two supplementary questions for the
30 | SPEECH | 1072 | Er Dr Lee Bee Wah (Nee Soon) | The second question: I think what we need is education, or
31 | SPEECH | 1098 | Mr Ong Ye Kung | The first question is whether there is a deep-rooted trend
32 | SPEECH | 1098 | Mr Ong Ye Kung | I do agree with the Member that we need to send a strong
33 | SPEECH | 1111 | Mr Speaker | Miss Cheryl Chan.
34 | SPEECH | 1024 | Miss Cheryl Chan Wei Ling (Fengshan) | I have two questions for Minister Ong Ye Kung. The first
35 | SPEECH | 1098 | Mr Ong Ye Kung | Sorry, I did not catch the Member's first question because
36 | SPEECH | 1024 | Miss Cheryl Chan Wei Ling | It is true. The thing is that if this incident was not
37 | SPEECH | 1098 | Mr Ong Ye Kung | Okay, I see. Should we not have done this earlier, in other
38 | SPEECH | 1098 | Mr Ong Ye Kung | The second question is how we would know if the measures
39 | SPEECH | 1111 | Mr Speaker | Mr Lim Biow Chuan.
40 | SPEECH | 1076 | Mr Lim Biow Chuan (Mountbatten) | Mr Speaker, I just wanted to ask the Minister, I thought 37
41 | SPEECH | 1076 | Mr Lim Biow Chuan (Mountbatten) | Can the reported cases of voyeurism be publicised in campus
42 | SPEECH | 1076 | Mr Lim Biow Chuan (Mountbatten) | And also, whether the Minister will consider asking the AUs
43 | SPEECH | 1098 | Mr Ong Ye Kung | The first question is again, looking back, why did we not
44 | SPEECH | 1098 | Mr Ong Ye Kung | As to publicising the punishment, NUS has actually been
45 | SPEECH | 1111 | Mr Speaker | Mr Leon Perera.
46 | SPEECH | 1100 | Mr Leon Perera (Non-Constituency Member) | I have one supplementary question for Second Minister
47 | SPEECH | 1056 | Ms Indranee Rajah | The short answer is that all the IHLs are reviewing their
48 | SPEECH | 1111 | Mr Speaker | Ms Anthea Ong.
49 | SPEECH | 1095 | Ms Anthea Ong (Nominated Member) | Can I ask the Minister, given that this is happening across
50 | SPEECH | 1056 | Ms Indranee Rajah | I think the first thing to remember is that it does not
51 | SPEECH | 1056 | Ms Indranee Rajah | The key thing is really making sure that individuals
52 | SPEECH | 1056 | Ms Indranee Rajah | Values, education, rehabilitation.
53 | SPEECH | 1111 | Mr Speaker | Mr Ang Wei Neng.
54 | SPEECH | 1021 | Mr Ang Wei Neng (Jurong) | Mr Speaker, I have a follow-up question for Second Minister
55 | SPEECH | 1056 | Ms Indranee Rajah | The students can and do visit their friends in other
56 | SPEECH | 1098 | Mr Ong Ye Kung | I just want to add that we need to take some firm measures
57 | SPEECH | 1111 | Mr Speaker | Ms Foo Mee Har.
58 | SPEECH | 1045 | Ms Foo Mee Har (West Coast) | Mr Speaker, I have three supplementary questions for the
59 | SPEECH | 1045 | Ms Foo Mee Har (West Coast) | Secondly, on the safety measures, what would be some
60 | SPEECH | 1098 | Mr Ong Ye Kung | I think we also need to respect the fact that they are AUs
61 | SPEECH | 1098 | Mr Ong Ye Kung | Having said that, when I first issued my public statement
62 | SPEECH | 1111 | Mr Speaker | Assoc Prof Walter Theseira.
63 | SPEECH | 1120 | Assoc Prof Walter Theseira (Nominated Member) | Mr Speaker, just two questions for the Minister. The first
64 | SPEECH | 1120 | Assoc Prof Walter Theseira (Nominated Member) | The second question is: when we look at the disciplinary
65 | SPEECH | 1098 | Mr Ong Ye Kung | The first question of inconsistencies across AUs, I would
66 | SPEECH | 1098 | Mr Ong Ye Kung | The second question is expertise. The disciplinary boards
"""
_REPORT_25170_TITLE = "SENNETT ESTATE"
_REPORT_25170_ROWS = """
1 | UNCLASSIFIED |  |  | The following Question stood in the name of Mr Chiam See Tong -
2 | DOCUMENT_TEXT |  |  | 2. To ask the Minister for National Development whether the recent decision to upgrade Sennett
3 | SPEECH | 723 | Mr Andy Gan Lai Chiang (Marine Parade) | Question No. 2, Sir.
4 | SPEECH | 792 | The Minister of State for National Development (Dr Vivian Balakrishnan) (for the Minister for National Development) | Mr Deputy Speaker, Sir, the decision to upgrade Sennett Estate is based on the eligibility of the
5 | SPEECH | 723 | Mr Andy Gan Lai Chiang | Can the Minister of State please elaborate on the extent of upgrading that is going to be provided?
6 | SPEECH | 792 | Dr Vivian Balakrishnan | Sir, the details of the upgrading for Sennett Estate are still being worked out. I think it would
"""
_REPORT_17169_TITLE = "Breakdown of Annual Expenditures of Autonomous Universities"
_REPORT_17169_ROWS = """
1 | SPEECH | 1012 | Mr Yee Jenn Jong | asked the Minister for Education since 2000 (a) what are the respective annual expenditures in
2 | SPEECH | 1012 | Mr Yee Jenn Jong | (vi) capital investment, facility maintenance and leases, for our universities; and (b) for each
3 | SPEECH | 937 | Mr Heng Swee Keat | In Financial Year (FY) 2006, expenditure on manpower was $1.1 billion and other operating
"""
_REPORT_23702_TITLE = "CAUSEWAY AND SECOND LINK"
_REPORT_23702_ROWS = """
1 | UNCLASSIFIED |  |  | The following Questions stood in the names of Ms Indranee Rajah, Mr Ong Kian Min and Mdm Ho Geok Choo respectively -
2 | UNCLASSIFIED |  |  | 9. To ask the Deputy Prime Minister and Minister for Home
3 | UNCLASSIFIED |  |  | 10. To ask the Deputy Prime Minister and Minister for Home
4 | UNCLASSIFIED |  |  | 11. To ask the Deputy Prime Minister and Minister for Home
5 | SPEECH | 773 | Mr Ong Kian Min (Tampines) | Question No. 9, Sir.
6 | SPEECH | 732 | The Senior Minister of State for Home Affairs (Assoc. Prof. Ho Peng Kee) (for the Deputy Prime Minister and Minister for Home Affairs) | Mr Speaker, Sir, can I have your permission to take
7 | SPEECH | 702 | Mr Speaker | Yes, you may.
8 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | Mr Speaker, Sir, our borders are our first line of defence
9 | HEADING |  |  | _Reasons for congestion at the land checkpoints_
10 | HEADING |  |  | _Stepped-up security checks_
11 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | Sir, these enhanced security checks have been effective in
12 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | In addition, 250 cases of foreigners trying to enter
13 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | Since the introduction of the Biometric Database for
14 | HEADING |  |  | _Increased traffic volume_
15 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | Sir, whilst enhanced security is one reason for congestion
16 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | For example, comparing 2004 and 2005, in the month of
17 | HEADING |  |  | _Changes in traffic patterns_
18 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | Sir, the situation is exacerbated by changes in traffic
19 | HEADING |  |  | _Motorists' inconsiderate behaviour_
20 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | On top of these two reasons, the lack of lane discipline
21 | HEADING |  |  | _Measures taken to ease congestion at the land checkpoints_
22 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | Sir, having stated the reasons for congestion at our land
23 | HEADING |  |  | _Increasing manpower_
24 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | Thus, more ICA officers have been put to work over-time and
25 | HEADING |  |  | _Leveraging on technology_
26 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | Besides manpower adjustments, we will also continue to
27 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | ICA also intends to implement the Enhanced-Immigration
28 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | _Changi_ _Airport_ _immigration clearance procedures_
29 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | Mdm Ho Geok Choo asked if it is possible to adopt Changi
30 | HEADING |  |  | _Playing a part - travellers_
31 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | Sir, travellers can also play a part in helping to ease
32 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | Furthermore, they can make sure that they do not bring
33 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | In summary, Sir, ICA will continue to take the necessary
34 | SPEECH | 773 | Mr Ong Kian Min | Sir, I would like to ask the Senior Minister of State about
35 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | Sir, no checks will be foolproof, but I think we must do
36 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | For bus passengers, the procedure is that when the buses
37 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | But for cars, with the 100% checks, all the cars are
38 | SPEECH | 713 | Mr Steve Chia Kiah Hong | Sir, I agree with him that the issue is having more
39 | SPEECH | 732 | Assoc. Prof. Ho Peng Kee | I am not sure we can expect once-and-for-all solution
"""
_REPORT_21480_TITLE = "PRESIDENTIAL ELECTIONS (AMENDMENT) BILL"
_REPORT_21480_ROWS = """
1 | PROCEDURAL |  |  | Order for Second Reading read.
2 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | Mr Deputy Speaker, Sir, thank you for the indulgence granted.
3 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | Sir, I beg to move, "That the Bill be now read a Second time."
4 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | This Bill amends the Presidential Elections Act.
5 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | The Presidential Elections are run in a similar manner as parliamentary
6 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | There are three main amendments to the Act. First, it provides for a
7 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | Cooling-Off day_
8 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | Sir, the most significant amendment in the Bill is the introduction of a
9 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | The secondary advantage of having a Cooling-Off day is that it reduces any
10 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | The Bill increases the minimum period between Nomination Day and Polling Day by
11 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | Presidential candidates will be allowed television broadcasts on Cooling-Off
12 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | The Bill will also clarify that election rally permits are needed before
13 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | _Election contingencies
14 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | Sir, the Bill introduces a range of contingency measures to deal with crisis
15 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | _Review of election offences
16 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | _ Finally, although the Presidential Elections Act was enacted much later, in
17 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | The Bill therefore proposes amendments to the maximum penalties of offences in
18 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | We are also introducing a new offence that prohibits individuals other than
19 | SPEECH | 836 | The Minister for Law (Mr K Shanmugam) | Sir, I beg to move.
20 | PROCEDURAL |  |  | Question put, and agreed to.
21 | PROCEDURAL |  |  | Bill accordingly read a Second time and committed to a Committee of the whole
22 | PROCEDURAL |  |  | The House immediately resolved itself into a Committee on the Bill. – [Mr
23 | PROCEDURAL |  |  | Bill considered in Committee; reported without amendment; read a Third time and
"""
_REPORT_25173_TITLE = "ANNEX - ECONOMIC RESTRUCTURING SHARES"
_REPORT_25173_ROWS = """
1 | DOCUMENT_TEXT |  |  | Annex - Singaporeans who did not qualify for ERS (Cols. 2273 - 2274)
"""
_REPORT_42200_TITLE = (
    "QUESTIONS FOR ORAL ANSWER STOOD OVER TO NEXT AVAILABLE SITTING OF PARLIAMENT"
)
_REPORT_42200_ROWS = """
1 | UNCLASSIFIED |  |  | Appendix I
2 | SPEECH | 237 | Mr Ngeow Pack Hua | To ask the Minister for Trade and Industry whether he is aware that ventilation in Boon Lay Garden
3 | SPEECH | 248 | Mr Rohan bin Kamis | To ask the Minister for Trade and Industry what are the plans to enlarge the facilities of Sentosa
4 | SPEECH | 219 | Mr Ho See Beng | To ask the Minister for National Development whether the Raffles Centre development project will
5 | SPEECH | 252 | Haji Sha'ari bin Tadin | To ask the Minister for National Development if he will request the Public Works Department to
6 | SPEECH | 252 | Haji Sha'ari bin Tadin | To ask the Minister for National Development if he will consider installing traffic lights at the
7 | SPEECH | 267 | Mr Eugene Yap Giau Cheng | To ask the Minister for National Development (a) when he proposes to bring the Sale of Commercial
8 | SPEECH | 246 | Haji Rahmat bin Kenap | To ask the Minister for Social Affairs whether there is sufficient manpower for the ambulances as,
9 | SPEECH | 226 | Dr Lau Teik Soon | To ask the Minister for Social Affairs when construction of the Sports Centre at Burghley Drive
10 | SPEECH | 246 | Haji Rahmat bin Kenap | To ask the Minister for National Development whether the Housing and Development Board will
11 | SPEECH | 218 | Mr Ho Kah Leong | To ask the Minister for National Development if the Public Works Department will erect proper signs
12 | SPEECH | 224 | Dr Koh Lip Lin | To ask the Minister for National Development (a) if the development plan for Nee Soon New Town has
13 | SPEECH | 226 | Dr Lau Teik Soon | To ask the Minister for National Development whether he will consider installing a traffic light
14 | SPEECH | 255 | Encik Sidek bin Saniff | To ask the Minister for National Development if he will consider allowing the conversion of three
15 | SPEECH | 255 | Encik Sidek bin Saniff | The following Question has been withdrawn:
16 | SPEECH | 246 | Haji Rahmat bin Kenap | To ask the Minister for National Development whether farmers affected by redevelopment can be
"""
_REPORT_32864_TITLE = "HOUSING AND DEVELOPMENT BOARD ESTATES"
_REPORT_32864_ROWS = """
1 | UNCLASSIFIED |  |  | The following Question on the Order Paper has been postponed to Tuesday, 22nd March, 1983:
2 | SPEECH | 314 | Mr M.K.A. Jabbar | To ask the Minister for the Environment, as cleanliness in Housing and Development Board estates
"""
_REPORT_39111_TITLE = "GOVERNMENT CHINESE SECONDARY IV EXAMINATION"
_REPORT_39111_ROWS = """
1 | SPEECH | 1377 | Mrs Seow Peck Leng | (by Private Notice under Standing Order No. 18 (1) asked the Minister for Education (i) whether he
2 | SPEECH | 64 | Mr Yong Nyuk Lin | Mr Speaker, Sir, I wish to state that the Government is fully aware of political agitators stopping
3 | SPEECH | 64 | Mr Yong Nyuk Lin | As regards the steps which Government should take, as I already stated yesterday, parents should
4 | SPEECH | 64 | Mr Yong Nyuk Lin | Parents of those misinformed children who joined the picket lines would do well to assert their
5 | SPEECH | 64 | Mr Yong Nyuk Lin | It is not the Government's intention to give the Communists the excuse to say that the police are
6 | SPEECH | 64 | Mr Yong Nyuk Lin | I wish to add that, despite intensive picketing today with human chains, blocking up all gates of
7 | CHAMBER_EVENT |  |  | Mrs Seow Peck Leng (Mountbatten) rose -
8 | SPEECH | 1352 | Mr Speaker | Mrs Seow, a supplementary question?
9 | SPEECH | 1377 | Mrs Seow Peck Leng | Supplementary, Sir. Mr Speaker, Sir, I wonder whether the Minister would consider taking this
10 | SPEECH | 1352 | Mr Speaker | Order. Will the hon. Member come to her supplementary question?
11 | SPEECH | 1377 | Mrs Seow Peck Leng | Would the Minister take the first immediate step to inform students through the radio, Rediffusion
12 | SPEECH | 30 | The Prime Minister (Mr Lee Kuan Yew) | Democratic methods!
13 | SPEECH | 64 | Mr Yong Nyuk Lin | Mr Speaker, Sir, I think it is a little difficult to insist upon the wearing of uniform as a
14 | SPEECH | 1377 | Mrs Seow Peck Leng | On a point of information.
15 | SPEECH | 1352 | Mr Speaker | If the Minister gives way.
16 | SPEECH | 64 | Mr Yong Nyuk Lin | I thought the Member for Mountbatten was suggesting that students should be informed that they
17 | SPEECH | 1377 | Mrs Seow Peck Leng | Without uniforms, because they are recognised by their uniforms.
18 | SPEECH | 64 | Mr Yong Nyuk Lin | As I have said, we should not make it so that to take an examination, you should be wearing a
19 | SPEECH | 64 | Mr Yong Nyuk Lin | I think, Sir, if we are to survive as a democratic State, we should be prepared to stand on our two
20 | SPEECH |  | Some hon. Members | Hear, hear!
21 | SPEECH | 64 | Mr Yong Nyuk Lin | - as we do to secret society gangsters. Unless we are prepared to fight for our rights, there is
22 | SPEECH | 1349 | Mr David Marshall (Anson) | Mr Speaker, Sir, may I ask the Minister whether there have been any incidents of violence or force
23 | SPEECH | 64 | Mr Yong Nyuk Lin | I am pleased to say, Sir, that up to this moment, there has been no report of any violence
24 | SPEECH | 1350 | Tun Lim Yew Hock (Cairnhill) | Sir, can the Minister say whether the agitation that is now taking place is following the same
25 | SPEECH | 1352 | Mr Speaker | That is a completely different question.
26 | SPEECH | 1377 | Mrs Seow Peck Leng | Mr Speaker, Sir, I wonder whether the Minister would do for those who were not able to take their
27 | SPEECH | 64 | Mr Yong Nyuk Lin | If it is true that they were prevented through sheer intimidation from taking the paper today, the
28 | SPEECH | 1377 | Mrs Seow Peck Leng | Thank you.
"""
_REPORT_38102_TITLE = "ADDENDUM PIONEER INDUSTRIES"
_REPORT_38102_ROWS = """
1 |  |  |  | Dr Goh Keng Swee, pursuant to his written answer to the following question on 18th November, 1964
2 |  |  |  | "Mr Ong Eng Guan asked the Minister for Finance to state the number of Pioneer Certificates which
3 |  |  |  | [APPENDIX TO WRITTEN ANSWER(Pages 1 -
"""
_REPORT_30113_TITLE = "FOOD POISONING CASES"
_REPORT_30113_ROWS = """
1 | DOCUMENT_TEXT |  |  | 6. To ask the Minister for the Environment which areas in Singapore have the highest number of food
2 | SPEECH | 500 | Dr Aline K Wong (Tampines GRC) | Question No. 6, Sir.
3 | SPEECH | 429 | Dr Ahmad Mattar | Mr Speaker, Sir, a total of 120 incidents of food poisoning were reported during the first seven
4 | SPEECH | 429 | Dr Ahmad Mattar | Most of the food poisoning incidents were traced to restaurants (39 incidents), eating houses (26
5 | SPEECH | 429 | Dr Ahmad Mattar | Of the 39 restaurants implicated, 18 were located in the city area. In the case of eating houses,
"""
_REPORT_41305_TITLE = "ADDENDUM - GOVERNMENT PRIMARY SCHOOLS"
_REPORT_41305_ROWS = """
1 | SPEECH | 1354 | Mr Chew Swee Kee | , pursuant to his reply to the following question for oral answer asked on 4th April, 1956
2 | SPEECH | 1396 | "Mr John Ede | asked the Minister for Education (i) how many new students were admitted to Government primary
3 | SPEECH | 1396 | "Mr John Ede | supplied the following information:
4 | SPEECH | 1396 | "Mr John Ede | (i) 15,553.
5 | SPEECH | 1396 | "Mr John Ede | (ii) (a) 10,116.
6 | SPEECH | 1396 | "Mr John Ede | (b) No Singapore children were refused admission. As far as the Ministry of Education has been able
7 | SPEECH | 1396 | "Mr John Ede | (iii) 4,849.
8 | SPEECH | 1396 | "Mr John Ede | It will be observed that the figures in (ii) (a) and (iii) together come to nearly 600 less than
"""
_REPORT_11779_TITLE = "Measures to Prevent Unauthorised Entry into Singapore as Piracies Spike in Singapore Straits"
_REPORT_11779_ROWS = """
1 | SPEECH | 1106 | Mr Seah Kian Peng | asked the Minister for Defence in light of the recent spike in piracies along the Singapore Strait,
2 | SPEECH |  | Mr Deputy Speaker | Questions for Oral Answer. Question No 1. Mr Seah Kian Peng.
3 | SPEECH | 1106 | Mr Seah Kian Peng (Marine Parade) | Mr Deputy Speaker, Sir, could I get your permission to request for withdrawal of my question
4 | SPEECH |  | Mr Deputy Speaker | Yes, I give my consent. Mr Leon Perera.
"""
_REPORT_25149_TITLE = "SURVEY ON ELDERSHIELD SCHEME"
_REPORT_25149_ROWS = """
1 | SPEECH | 725 | Mr Gan Kim Yong | asked the Minister for Health whether the proposed survey on the ElderShield Scheme has been
2 | SPEECH | 752 | Mr Lim Hng Kiang | Mr Speaker, Sir, the Ministry has asked the two ElderShield insurers to consider doing a survey to
3 | SPEECH | 752 | Mr Lim Hng Kiang | On the main reason for their opting out of ElderShield, 23% indicated that they could not afford
4 | SPEECH | 752 | Mr Lim Hng Kiang | Great Eastern is conducting a similar survey, which will be completed in March. The Ministry will
5 | SPEECH | 725 | Mr Gan Kim Yong (Holland-Bukit Panjang) | May I ask the Minister whether there is any specific timeframe for the revision of the new scheme.
6 | SPEECH | 752 | Mr Lim Hng Kiang | The ElderShield scheme was launched very recently. The immediate priority of the Ministry and the
"""


def test_report_11789_filer_whose_question_rows_are_printed_has_a_reader_and_an_answerer_for_another_minister() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_11789_TITLE,
        _REPORT_11789_ROWS,
        printed_name_to_speaker_id={"Mr Christopher de Souza": 1033},
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ABSENT_FILER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr Christopher de Souza",
            1033,
        ),
        (
            ParticipantRole.CHAIR,
            ParticipantRoleSource.CHAIR_LABEL,
            4,
            "Mr Speaker",
            1111,
        ),
        (
            ParticipantRole.READER,
            ParticipantRoleSource.ASKER_RULES,
            5,
            "Mr Cedric Foo Chee Keng (Pioneer)",
            1043,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            6,
            "The Senior Parliamentary Secretary to the Minister for Home Affairs (Ms Sun Xueling) (for the Minister for Home Affairs)",
            1109,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
            16,
            "Mr Christopher de Souza (Holland-Bukit Timah)",
            1033,
        ),
    ]
    assert _summarise_office_marks(labelled_report.participants) == [
        (
            ParticipantRole.CHAIR,
            1111,
            None,
            "Mr Speaker",
            OfficeClass.OTHER,
            OfficeSource.LABEL_IN_REPORT,
        ),
        (
            ParticipantRole.ANSWERER,
            1109,
            "for the Minister for Home Affairs",
            "The Senior Parliamentary Secretary to the Minister for Home Affairs",
            OfficeClass.SENIOR_PARLIAMENTARY_SECRETARY,
            OfficeSource.LABEL_IN_REPORT,
        ),
    ]
    assert _summarise_states(labelled_report.states) == []


def test_report_18268_absent_filer_who_arrives_asks_a_follow_up() -> None:
    labelled_report = _label_report(
        _REPORT_18268_TITLE,
        _REPORT_18268_ROWS,
        printed_name_to_speaker_id={"Mr R Dhinakaran": 987},
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ABSENT_FILER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr R Dhinakaran",
            987,
        ),
        (
            ParticipantRole.READER,
            ParticipantRoleSource.ASKER_RULES,
            4,
            "Mr Patrick Tay Teck Guan (Nee Soon)",
            984,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            5,
            "The Acting Minister for Manpower (Mr Tan Chuan-Jin)",
            995,
        ),
        (
            ParticipantRole.CHAIR,
            ParticipantRoleSource.CHAIR_LABEL,
            8,
            "Mdm Speaker",
            934,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
            12,
            "Mr R Dhinakaran",
            987,
        ),
    ]
    assert _summarise_states(labelled_report.states) == []


def test_report_45746_deputy_speaker_who_asks_and_follows_up_later_takes_the_chair() -> (
    None
):
    labelled_report = _label_report(_REPORT_45746_TITLE, _REPORT_45746_ROWS)

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr Sharael Taha",
            1216,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            2,
            "Ms He Ting Ru",
            1164,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            3,
            "Miss Rachel Ong",
            1208,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            5,
            "Ms Jessica Tan Soon Neo",
            1172,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            7,
            "Ms Hazel Poa",
            1205,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            8,
            "Mr Edward Chia Bing Hui",
            1153,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            9,
            "Miss Cheng Li Hui",
            1142,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            10,
            "Mr Liang Eng Hwa",
            1183,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            13,
            "Mr Desmond Choo",
            1150,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            14,
            "Ms Ng Ling Ling",
            1198,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            15,
            "The Senior Minister of State for Manpower (Mr Zaqy Mohamad) (for the Minister of Manpower)",
            1239,
        ),
        (
            ParticipantRole.CHAIR,
            ParticipantRoleSource.CHAIR_LABEL,
            16,
            "Mr Speaker",
            1223,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
            56,
            "Ms Jessica Tan Soon Neo (East Coast)",
            1172,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
            63,
            "Ms Hazel Poa (Non-Constituency Member)",
            1205,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
            70,
            "Mr Edward Chia Bing Hui (Holland-Bukit Timah)",
            1153,
        ),
        (
            ParticipantRole.CHAIR,
            ParticipantRoleSource.CHAIR_LABEL,
            79,
            "Mdm Deputy Speaker",
            1172,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            80,
            "Mr Gerald Giam Yean Song (Aljunied)",
            1160,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            89,
            "Mr Yip Hon Weng (Yio Chu Kang)",
            1238,
        ),
    ]
    assert _summarise_office_marks(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            1172,
            None,
            "Mdm Deputy Speaker",
            OfficeClass.OTHER,
            OfficeSource.LABEL_IN_REPORT,
        ),
        (
            ParticipantRole.ANSWERER,
            1239,
            "for the Minister of Manpower",
            "The Senior Minister of State for Manpower",
            OfficeClass.SENIOR_MINISTER_OF_STATE,
            OfficeSource.LABEL_IN_REPORT,
        ),
        (
            ParticipantRole.CHAIR,
            1223,
            None,
            "Mr Speaker",
            OfficeClass.OTHER,
            OfficeSource.LABEL_IN_REPORT,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            1172,
            None,
            "Mdm Deputy Speaker",
            OfficeClass.OTHER,
            OfficeSource.LABEL_IN_REPORT,
        ),
        (
            ParticipantRole.CHAIR,
            1172,
            None,
            "Mdm Deputy Speaker",
            OfficeClass.OTHER,
            OfficeSource.LABEL_IN_REPORT,
        ),
    ]
    assert _summarise_states(labelled_report.states) == []


def test_report_6147_chair_holders_name_call_is_a_chair_row_and_no_supplementary() -> (
    None
):
    labelled_report = _label_report(_REPORT_6147_TITLE, _REPORT_6147_ROWS)

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Ms Denise Phua Lay Peng",
            1148,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            2,
            "The Minister for Education (Mr Chan Chun Sing)",
            1137,
        ),
        (
            ParticipantRole.CHAIR,
            ParticipantRoleSource.CHAIR_LABEL,
            9,
            "Mr Deputy Speaker",
            1144,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
            10,
            "Ms Denise Phua Lay Peng (Jalan Besar)",
            1148,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            17,
            "Mr Leong Mun Wai (Non-Constituency Member)",
            1182,
        ),
    ]
    assert _summarise_states(labelled_report.states) == []


def test_name_call_before_the_first_chair_label_is_that_persons_chair_row() -> None:
    rows_text = """
1 | SPEECH | 10 | Ms Asker One | asked the Minister for Education about schools.
2 | SPEECH | 20 | Mr Chair Holder | Minister Tan Chuan-Jin.
3 | SPEECH | 30 | The Minister for Education (Mr Tan Chuan-Jin) | Sir, the answer is yes.
4 | SPEECH | 20 | Mr Deputy Speaker | Order.
5 | SPEECH | 20 | Mr Chair Holder | Minister Tan Chuan-Jin.
"""

    labelled_report = _label_report("Schools", rows_text)

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Ms Asker One",
            10,
        ),
        (
            ParticipantRole.CHAIR,
            ParticipantRoleSource.CHAIR_NAME_CALL,
            2,
            "Mr Chair Holder",
            20,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            3,
            "The Minister for Education (Mr Tan Chuan-Jin)",
            30,
        ),
    ]


def test_collective_label_before_the_answer_is_unlabelled() -> None:
    rows_text = """
1 | SPEECH | 10 | Ms Asker One | asked the Minister for Education about schools.
2 | SPEECH |  | Some hon. Members | Hear, hear.
3 | SPEECH | 30 | The Minister for Education (Mr Tan Chuan-Jin) | Sir, the answer is yes.
"""

    labelled_report = _label_report("Schools", rows_text)

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Ms Asker One",
            10,
        ),
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            2,
            "Some hon. Members",
            None,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            3,
            "The Minister for Education (Mr Tan Chuan-Jin)",
            30,
        ),
    ]


def test_collective_label_is_never_the_answerer_by_position() -> None:
    rows_text = """
1 | SPEECH | 10 | Ms Asker One | asked the Minister for Education about schools.
2 | SPEECH |  | An hon. Member | Is it true?
3 | SPEECH | 30 | Mr Somebody | Sir, the answer is yes.
"""

    labelled_report = _label_report("Schools", rows_text)

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Ms Asker One",
            10,
        ),
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            2,
            "An hon. Member",
            None,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.POSITION,
            3,
            "Mr Somebody",
            30,
        ),
    ]


def test_answer_after_the_question_starts_the_follow_ups_when_the_minister_spoke_first() -> (
    None
):
    rows_text = """
1 | SPEECH | 30 | The Minister for Education (Mr Tan Chuan-Jin) | Mr Speaker, I will take this question first.
2 | SPEECH | 10 | Ms Asker One | asked the Minister for Education about schools.
3 | SPEECH | 10 | Ms Asker One | She also asks about the cost of the schemes.
4 | SPEECH | 30 | The Minister for Education (Mr Tan Chuan-Jin) | Sir, the answer is yes.
5 | SPEECH | 10 | Ms Asker One | Can the Minister say more?
"""

    labelled_report = _label_report("Schools", rows_text)

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            1,
            "The Minister for Education (Mr Tan Chuan-Jin)",
            30,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            2,
            "Ms Asker One",
            10,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
            5,
            "Ms Asker One",
            10,
        ),
    ]


def test_report_6095_written_answer_answerer_has_the_office_of_the_day() -> None:
    labelled_report = _label_report(
        _REPORT_6095_TITLE,
        _REPORT_6095_ROWS,
        speaker_id_to_office={
            1175: Office(
                "Minister for Home Affairs and Law", OfficeSource.ATTENDANCE_LIST
            )
        },
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr Melvin Yong Yik Chye",
            1190,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            2,
            "Mr K Shanmugam",
            1175,
        ),
    ]
    assert _summarise_office_marks(labelled_report.participants) == [
        (
            ParticipantRole.ANSWERER,
            1175,
            None,
            "Minister for Home Affairs and Law",
            OfficeClass.MINISTER,
            OfficeSource.ATTENDANCE_LIST,
        )
    ]
    assert _summarise_states(labelled_report.states) == []


def test_report_19273_written_answer_for_the_prime_minister_keeps_the_for_bracket() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_19273_TITLE,
        _REPORT_19273_ROWS,
        speaker_id_to_office={
            1001: Office(
                "Deputy Prime Minister and Coordinating Minister for National Security and Minister for Home Affairs",
                OfficeSource.ATTENDANCE_LIST,
            )
        },
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Asst Prof Tan Kheng Boon Eugene",
            996,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            2,
            "Mr Teo Chee Hean (for the Prime Minister)",
            1001,
        ),
    ]
    assert _summarise_office_marks(labelled_report.participants) == [
        (
            ParticipantRole.ANSWERER,
            1001,
            "for the Prime Minister",
            "Deputy Prime Minister and Coordinating Minister for National Security and Minister for Home Affairs",
            OfficeClass.DEPUTY_PRIME_MINISTER,
            OfficeSource.ATTENDANCE_LIST,
        )
    ]


def test_report_11034_two_ministers_answer_and_two_askers_follow_up() -> None:
    labelled_report = _label_report(_REPORT_11034_TITLE, _REPORT_11034_ROWS)

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr Murali Pillai",
            1195,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            2,
            "Dr Tan Wu Meng",
            1224,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            4,
            "Mr Vikram Nair",
            1232,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            5,
            "Mr Leong Mun Wai",
            1182,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            6,
            "Mr Louis Ng Kok Kwang",
            1199,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            7,
            "Mr Liang Eng Hwa",
            1183,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            8,
            "Mr Derrick Goh",
            1161,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            11,
            "Mr Zhulkarnain Abdul Rahim",
            1240,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            12,
            "Mr Lim Biow Chuan",
            1184,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            14,
            "The Minister of State for Home Affairs (Mr Desmond Tan) (on behalf of the Minister for Home Affairs and Law)",
            1152,
        ),
        (
            ParticipantRole.CHAIR,
            ParticipantRoleSource.CHAIR_LABEL,
            15,
            "Mr Speaker",
            1223,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
            17,
            "Mr Murali Pillai (Bukit Batok)",
            1195,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            21,
            "The Minister for Home Affairs and Minister for Law (Mr K Shanmugam)",
            1175,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
            23,
            "Mr Leong Mun Wai (Non-Constituency Member)",
            1182,
        ),
    ]
    assert _summarise_office_marks(labelled_report.participants) == [
        (
            ParticipantRole.ANSWERER,
            1152,
            "on behalf of the Minister for Home Affairs and Law",
            "The Minister of State for Home Affairs",
            OfficeClass.MINISTER_OF_STATE,
            OfficeSource.LABEL_IN_REPORT,
        ),
        (
            ParticipantRole.CHAIR,
            1223,
            None,
            "Mr Speaker",
            OfficeClass.OTHER,
            OfficeSource.LABEL_IN_REPORT,
        ),
        (
            ParticipantRole.ANSWERER,
            1175,
            None,
            "The Minister for Home Affairs and Minister for Law",
            OfficeClass.MINISTER,
            OfficeSource.LABEL_IN_REPORT,
        ),
    ]
    assert _summarise_states(labelled_report.states) == []


def test_report_44970_second_minister_with_a_bare_label_is_an_answerer_by_office_on_the_day() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_44970_TITLE,
        _REPORT_44970_ROWS,
        speaker_id_to_office={
            1098: Office("Minister for Education", OfficeSource.ATTENDANCE_LIST)
        },
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Ms Tin Pei Ling",
            1121,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            2,
            "Ms Foo Mee Har",
            1045,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            3,
            "Mr Muhamad Faisal Bin Abdul Manap",
            1088,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            5,
            "The Second Minister for Education (Ms Indranee Rajah) (for the Minister for Education)",
            1056,
        ),
        (
            ParticipantRole.CHAIR,
            ParticipantRoleSource.CHAIR_LABEL,
            6,
            "Mr Speaker",
            1111,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            29,
            "Er Dr Lee Bee Wah (Nee Soon)",
            1072,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            31,
            "Mr Ong Ye Kung",
            1098,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            34,
            "Miss Cheryl Chan Wei Ling (Fengshan)",
            1024,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            40,
            "Mr Lim Biow Chuan (Mountbatten)",
            1076,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            46,
            "Mr Leon Perera (Non-Constituency Member)",
            1100,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            49,
            "Ms Anthea Ong (Nominated Member)",
            1095,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            54,
            "Mr Ang Wei Neng (Jurong)",
            1021,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
            58,
            "Ms Foo Mee Har (West Coast)",
            1045,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            63,
            "Assoc Prof Walter Theseira (Nominated Member)",
            1120,
        ),
    ]
    assert _summarise_office_marks(labelled_report.participants) == [
        (
            ParticipantRole.ANSWERER,
            1056,
            "for the Minister for Education",
            "The Second Minister for Education",
            OfficeClass.MINISTER,
            OfficeSource.LABEL_IN_REPORT,
        ),
        (
            ParticipantRole.CHAIR,
            1111,
            None,
            "Mr Speaker",
            OfficeClass.OTHER,
            OfficeSource.LABEL_IN_REPORT,
        ),
        (
            ParticipantRole.ANSWERER,
            1098,
            None,
            "Minister for Education",
            OfficeClass.MINISTER,
            OfficeSource.ATTENDANCE_LIST,
        ),
    ]
    assert _summarise_states(labelled_report.states) == []


def test_report_25170_reader_who_asks_a_supplementary_is_a_supplementary_asker() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_25170_TITLE,
        _REPORT_25170_ROWS,
        printed_name_to_speaker_id={"Mr Chiam See Tong": 714},
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ABSENT_FILER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr Chiam See Tong",
            714,
        ),
        (
            ParticipantRole.READER,
            ParticipantRoleSource.ASKER_RULES,
            3,
            "Mr Andy Gan Lai Chiang (Marine Parade)",
            723,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            4,
            "The Minister of State for National Development (Dr Vivian Balakrishnan) (for the Minister for National Development)",
            792,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            5,
            "Mr Andy Gan Lai Chiang",
            723,
        ),
    ]
    assert _summarise_states(labelled_report.states) == []


def test_report_17169_askers_continuation_paragraph_before_the_answer_is_no_follow_up() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_17169_TITLE,
        _REPORT_17169_ROWS,
        speaker_id_to_office={
            937: Office("Minister for Education", OfficeSource.ATTENDANCE_LIST)
        },
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr Yee Jenn Jong",
            1012,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            3,
            "Mr Heng Swee Keat",
            937,
        ),
    ]
    assert _summarise_states(labelled_report.states) == []


def test_report_23702_three_filers_of_one_stood_line_are_numbered_in_candidate_order() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_23702_TITLE,
        _REPORT_23702_ROWS,
        printed_name_to_speaker_id={
            "Ms Indranee Rajah": 734,
            "Mr Ong Kian Min": 773,
            "Mdm Ho Geok Choo": 731,
        },
    )

    assert [
        report_participant.ordinal
        for report_participant in labelled_report.participants
    ] == [1, 2, 3, 4, 5, 6, 7]
    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ABSENT_FILER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Ms Indranee Rajah",
            734,
        ),
        (
            ParticipantRole.ABSENT_FILER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr Ong Kian Min",
            773,
        ),
        (
            ParticipantRole.ABSENT_FILER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mdm Ho Geok Choo",
            731,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            6,
            "The Senior Minister of State for Home Affairs (Assoc. Prof. Ho Peng Kee) (for the Deputy Prime Minister and Minister for Home Affairs)",
            732,
        ),
        (
            ParticipantRole.CHAIR,
            ParticipantRoleSource.CHAIR_LABEL,
            7,
            "Mr Speaker",
            702,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
            34,
            "Mr Ong Kian Min",
            773,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            38,
            "Mr Steve Chia Kiah Hong",
            713,
        ),
    ]


def test_report_30113_numbered_question_with_no_asker_leaves_the_caller_unlabelled() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_30113_TITLE,
        _REPORT_30113_ROWS,
        speaker_id_to_office={
            429: Office("Minister for the Environment", OfficeSource.ATTENDANCE_LIST)
        },
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            2,
            "Dr Aline K Wong (Tampines GRC)",
            500,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            3,
            "Dr Ahmad Mattar",
            429,
        ),
    ]
    assert _summarise_states(labelled_report.states) == []


def test_report_21480_bill_reading_is_not_a_question() -> None:
    labelled_report = _label_report(_REPORT_21480_TITLE, _REPORT_21480_ROWS)

    assert _summarise_participants(labelled_report.participants) == []
    assert _summarise_states(labelled_report.states) == [
        (QuestionState.NOT_A_QUESTION, "PRESIDENTIAL ELECTIONS (AMENDMENT) BILL", None)
    ]


def test_report_25173_annex_title_is_not_a_question() -> None:
    labelled_report = _label_report(_REPORT_25173_TITLE, _REPORT_25173_ROWS)

    assert _summarise_participants(labelled_report.participants) == []
    assert _summarise_states(labelled_report.states) == [
        (QuestionState.NOT_A_QUESTION, "ANNEX - ECONOMIC RESTRUCTURING SHARES", None)
    ]


@pytest.mark.parametrize(
    "title",
    [
        "ANNEX A - ELDERSHIELD SCHEME",
        "APPENDIX - ELECTRICITY TARIFFS",
    ],
)
def test_title_of_an_annex_or_appendix_with_a_question_row_and_no_asker_is_not_a_question(
    title: str,
) -> None:
    not_a_question_state = get_not_a_question_state(title, [], [], frozenset({1}))

    assert not_a_question_state is not None
    assert not_a_question_state.state == QuestionState.NOT_A_QUESTION
    assert not_a_question_state.printed_text == title
    assert not_a_question_state.first_ordinal is None


def test_title_with_a_word_that_only_contains_table_or_list_is_a_question() -> None:
    assert (
        get_not_a_question_state(
            "Enforcement Actions Against Table Littering at Public Dining Spaces Since Implementation",
            [],
            [],
            frozenset({1}),
        )
        is None
    )


def test_title_of_an_annex_with_an_asker_is_a_question() -> None:
    asker_candidate = AskerCandidate(
        row_ordinal=1,
        source=ReportAskerSource.ASKED_LINE,
        printed_name="Mr Ong Eng Guan",
        speaker_id=1361,
        reader_printed_name=None,
        reader_speaker_id=None,
        reader_row_ordinal=None,
    )

    assert (
        get_not_a_question_state(
            "ANNEX A - ELDERSHIELD SCHEME", [], [asker_candidate], frozenset({1})
        )
        is None
    )


def test_report_42200_stood_over_list_has_the_title_state_and_no_participants() -> None:
    labelled_report = _label_report(
        _REPORT_42200_TITLE,
        _REPORT_42200_ROWS,
    )

    assert labelled_report.participants == []
    assert _summarise_states(labelled_report.states) == [
        (QuestionState.NOT_ASKED_ALOUD, _REPORT_42200_TITLE, None)
    ]


def test_report_42200_stood_over_list_title_is_not_asked_aloud_with_no_asker() -> None:
    question_states = get_question_states(
        _REPORT_42200_TITLE, _parse_rows(_REPORT_42200_ROWS), []
    )

    assert _summarise_states(
        build_report_question_states(_REPORT_ID, question_states)
    ) == [(QuestionState.NOT_ASKED_ALOUD, _REPORT_42200_TITLE, None)]


def test_report_32864_postponed_line_marks_the_question_not_asked_aloud() -> None:
    labelled_report = _label_report(_REPORT_32864_TITLE, _REPORT_32864_ROWS)

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            2,
            "Mr M.K.A. Jabbar",
            314,
        )
    ]
    assert _summarise_states(labelled_report.states) == [
        (
            QuestionState.NOT_ASKED_ALOUD,
            "The following Question on the Order Paper has been postponed to Tuesday, 22nd March, 1983:",
            1,
        )
    ]


def test_report_39111_private_notice_is_urgent() -> None:
    labelled_report = _label_report(
        _REPORT_39111_TITLE,
        _REPORT_39111_ROWS,
        speaker_id_to_office={
            64: Office("Minister for Education", OfficeSource.ATTENDANCE_LIST)
        },
    )

    assert _summarise_states(labelled_report.states) == [
        (
            QuestionState.URGENT,
            "(by Private Notice under Standing Order No. 18 (1) asked the Minister for Education (i) whether he",
            1,
        )
    ]


def test_report_38102_addendum_with_an_asker_is_a_correction() -> None:
    labelled_report = _label_report(
        _REPORT_38102_TITLE,
        _REPORT_38102_ROWS,
        printed_name_to_speaker_id={"Mr Ong Eng Guan": 1361},
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            2,
            "Mr Ong Eng Guan",
            1361,
        )
    ]
    assert _summarise_states(labelled_report.states) == [
        (QuestionState.CORRECTION, "ADDENDUM PIONEER INDUSTRIES", None)
    ]


def test_report_39111_some_hon_members_is_unlabelled() -> None:
    labelled_report = _label_report(
        _REPORT_39111_TITLE,
        _REPORT_39111_ROWS,
        speaker_id_to_office={
            64: Office("Minister for Education", OfficeSource.ATTENDANCE_LIST)
        },
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mrs Seow Peck Leng",
            1377,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            2,
            "Mr Yong Nyuk Lin",
            64,
        ),
        (
            ParticipantRole.CHAIR,
            ParticipantRoleSource.CHAIR_LABEL,
            8,
            "Mr Speaker",
            1352,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
            9,
            "Mrs Seow Peck Leng",
            1377,
        ),
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            12,
            "The Prime Minister (Mr Lee Kuan Yew)",
            30,
        ),
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            20,
            "Some hon. Members",
            None,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            22,
            "Mr David Marshall (Anson)",
            1349,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            24,
            "Tun Lim Yew Hock (Cairnhill)",
            1350,
        ),
    ]


def test_report_41305_minister_who_speaks_before_the_question_rows_is_the_answerer() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_41305_TITLE,
        _REPORT_41305_ROWS,
        speaker_id_to_office={
            1354: Office("Minister for Education", OfficeSource.ATTENDANCE_LIST)
        },
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            1,
            "Mr Chew Swee Kee",
            1354,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            2,
            '"Mr John Ede',
            1396,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
            3,
            '"Mr John Ede',
            1396,
        ),
    ]
    assert _summarise_states(labelled_report.states) == [
        (QuestionState.CORRECTION, "ADDENDUM - GOVERNMENT PRIMARY SCHOOLS", None)
    ]


def test_report_11779_request_to_withdraw_a_question_is_not_asked_aloud() -> None:
    labelled_report = _label_report(_REPORT_11779_TITLE, _REPORT_11779_ROWS)

    assert _summarise_states(labelled_report.states) == [
        (
            QuestionState.NOT_ASKED_ALOUD,
            "Mr Deputy Speaker, Sir, could I get your permission to request for withdrawal of my question",
            3,
        )
    ]


def test_report_25149_answerers_first_row_that_says_asked_the_is_the_answerers_first_row() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_25149_TITLE,
        _REPORT_25149_ROWS,
        speaker_id_to_office={
            752: Office(
                "Minister for Health and Second Minister for Finance",
                OfficeSource.ATTENDANCE_LIST,
            )
        },
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr Gan Kim Yong",
            725,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            2,
            "Mr Lim Hng Kiang",
            752,
        ),
        (
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
            5,
            "Mr Gan Kim Yong (Holland-Bukit Panjang)",
            725,
        ),
    ]


@pytest.mark.parametrize(
    "title",
    [
        pytest.param(
            "Criteria for Issuance of Correction Directions under Protection from Online Falsehoods and Manipulation Act",
            id="report_1329",
        ),
        pytest.param(
            "Correction of Information on Gov Factually Website", id="report_15397"
        ),
    ],
)
def test_title_naming_a_correction_that_is_not_an_addendum_gives_no_correction_state(
    title: str,
) -> None:
    assert get_question_states(title, [], []) == []


_REPORT_22647_TITLE = "INVESTMENTS BY GIC AND TEMASEK HOLDINGS IN UBS AND MERRILL LYNCH"
_REPORT_22647_ROWS = """
2 |  | 830 | Mr Inderjit Singh | asked the Minister for Finance (a) what is the rationale for the billion-dollar investments by GIC and
3 |  | 830 | Mr Inderjit Singh | Temasek Holdings in distressed banks like UBS and Merrill Lynch; (b) whether it was too early to make such investments especially since the full effect of the sub-prime crisis has yet to be quantified; and (c) whether he can assure the House that Singapore will not lose the money pumped into these two banks or its standing internationally.
4 |  | 889 | The Minister for Finance (Mr Tharman Shanmugaratnam) | Mr Speaker, Sir, Mr Inderjit Singh asked about the rationale for recent investments by GIC and Temasek in UBS and Merrill Lynch respectively, and asked whether it is premature to make such investments when the full effects of the sub-prime crisis have yet to be quantified.
5 |  | 889 | The Minister for Finance (Mr Tharman Shanmugaratnam) | Let me first state that GIC and Temasek make their investment decisions independent of each other, and of the Government. They make these decisions for commercial reasons, based on their own calculations, free of any influence from Government.
"""


def test_report_22647_speech_rows_with_no_kind_still_give_the_answerer() -> None:
    labelled_report = _label_report(
        _REPORT_22647_TITLE,
        _REPORT_22647_ROWS,
        printed_name_to_speaker_id={"Mr Inderjit Singh": 830},
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            2,
            "Mr Inderjit Singh",
            830,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            4,
            "The Minister for Finance (Mr Tharman Shanmugaratnam)",
            889,
        ),
    ]


_REPORT_37303_TITLE = "UNIFORM STANDARD OF DRESS FOR SCHOOL TEACHERS"
_REPORT_37303_ROWS = """
1 |  | 9 | Madam Chan Choy Siong | asked the Minister for Education whether he will take action to get all school teachers, both men and women, to observe a modest and uniform standard of dress as befits their profession as it has been seen that some school teachers are dressed indecorously in certain forms of ultra-modern attire when discharging their official duties.
2 |  | 1 | Inche Rahim Ishak (for the Minister for Education) | Mr Speaker, Sir, it is desirable that teachers should dress neatly and soberly when they are on duty -
3 |  | 64 | The Minister for Health (Mr Yong Nyuk Lin) | Look at me!
4 |  | 1 | Inche Rahim Ishak | -as the manner and mode of their dress will certainly have an influence on children under their charge.
5 |  | 1 | Inche Rahim Ishak | The hon. Member's point is well taken and teachers will be encouraged to dress decorously rather than decoratively when on duty.
6 |  | 1 | Inche Rahim Ishak | As for the Member's suggestion that teachers should wear a uniform standard of dress, the Ministry will seek the views of the various teachers' unions on the subject.
"""

_REPORT_15769_TITLE = "Re-employment of Women beyond Age 62"
_REPORT_15769_ROWS = """
1 |  | 1118 | Ms K Thanaletchimi | asked the Minister for Manpower (a) what is the current percentage of re-employment of female workers who have reached the age of (i) 62 years and (ii) 65 years; and (b) whether the Ministry will consider strategies to improve the employment of female workers beyond 62 in light of females having a longer lifespan.
2 |  | 1113 | The Minister of State for Manpower (Mr Sam Tan Chin Siong) (for the Minister for Manpower) | Mdm Speaker, the Ministry of Manpower (MOM) collects re-employment data regardless of their gender. In 2015, over 98% of local employees who wished to continue working were actually offered re-employment upon reaching the ages of 62 and 65. It shows that the re-employment rates for male and female workers, older workers, were both very high.
3 |  | 1113 | The Minister of State for Manpower (Mr Sam Tan Chin Siong) (for the Minister for Manpower) | The Government will continue to help older workers work for as long as they are willing and able to. And how do we do this? First, we will raise the re-employment age from 65 to 67 by 1 July 2017. We will also support employers with Special Employment Credit of up to 11% of wage offset when they employ workers aged 65 and above.
5 |  | 1052 | Mdm Speaker | Ms Thanaletchimi.
6 |  | 1118 | Ms K Thanaletchimi (Nominated Member) | I thank the Minister of State. Madam, just a supplementary question. Are there further strategies that we can embrace to ensure that older workers, especially the female cohort, could work longer in the workplace because it is important that they have sufficient savings, especially those low-wage workers and those who are middle income? They need to continue with their employment.
7 |  | 1118 | Ms K Thanaletchimi (Nominated Member) | The second supplementary question is: while the retirement and re-employment age has been raised to 67 by next year, in the meantime, what are the measures that we can take to ensure that these older workers will continue remaining in their employment, before this legislation is enacted?
8 |  | 1113 | Mr Sam Tan Chin Siong | Mdm Speaker, I thank the hon Member for raising two very important questions. Older workers have always been an important consideration in our work in MOM. This is why we have paid a lot of attention and also rolled out a lot of programmes to help older workers to get re-employed if they are willing and able to.
18 |  | 1052 | Mdm Speaker | Mr Murali Pillai.
19 |  | 1090 | Mr Murali Pillai (Bukit Batok) | Madam, given the time, I wonder whether this question can be held over. There is only one more minute.
20 |  | 1052 | Mdm Speaker | We have one minute, so the Minister of State can make his reply. If you can reply in one minute, Minister of State.
21 |  | 1039 | The Senior Minister of State for National Development (Mr Desmond Lee) | I can, Mdm Speaker.
22 |  | 1052 | Mdm Speaker | Yes, please, reply in one minute.
"""

_REPORT_21632_TITLE = "SCHEMES TO BOOST PRODUCTIVITY"
_REPORT_21632_ROWS = """
1 |  | 827 | Mdm Ho Geok Choo | asked the Minister for Manpower (a) how will schemes to boost productivity be implemented and who will implement them; (b) how will the indicators of success for these schemes be measured; and (c) how will the Ministry ensure that older workers are not replaced for the sake of boosting productivity.
2 |  | 881 | Assoc. Prof. Paulin Tay Straughan | asked the Minister of Manpower (a) if he will elaborate on the implications of the Economic Strategies Committee Report on older workers, especially with regard to the automation and mechanisation drive; and (b) what are the incentives for employers to invest in training and skills enhancement of older workers.
3 |  | 820 | The Minister for Manpower (Mr Gan Kim Yong) | Mr Speaker, Sir, the Economic Strategies Committee has recommended a major shift of our economy towards productivity-driven growth, rather than through the expansion of our workforce, so as to bring about higher incomes and a better standard of living for our people. To do so, we will need to restructure our economy to provide more room to grow and to grow more efficiently by having more productive enterprises, leveraging on innovation, optimising the use of resources and upgrading the quality and skills of our workforce. Contrary to the perception that improving productivity will result in job losses, productivity improvements can in fact help our economy and our enterprises remain competitive and save jobs for our workers – young and old, men and women, rank and file workers as well as Professionals, Managers, Executives and Technicians (PMETs). Raising productivity will also strengthen Singapore's position as an attractive investment location for growth industries. This will in turn create more quality jobs for Singaporeans. Specifically for older workers, despite the severe downturn in 2009, they have maintained their employment rate at 57% for those aged 55-64. The Government will continue to work closely with the Tripartite partners in preparing employers and employees for the re-employment legislation which will come into effect in 2012.
6 |  | 827 | Mdm Ho Geok Choo (West Coast) | Thank you, Minister for the very comprehensive response. Sir, the whole notion of productivity is about more output and better rewards. How do we reconcile this with the perception that older workers are less energetic and slower, and hence, to be pro-business, we need to reduce their compensation and rewards in two areas? Upon reaching 50 years of age, older workers face a reduction in CPF contribution and upon retirement, if they are found to be fit for re-employment, they are often re-employed at a reduced package. How we reconcile productivity with incentives in this instance? I would like to have Minister's comment on this.
7 |  | 820 | Mr Gan Kim Yong | Sir, the tripartite partners and the Ministry of Manpower have been working over the last few years to encourage our employers to adopt flexible wage systems that reflect the performance of our workers. We have also been working with the unions to encourage our workers to accept these arrangements and therefore, if our workers are able to be compensated according to the performance, then the seniority wage system will become less of an obstacle to older workers staying employed.
9 |  | 826 | The Minister of State, Prime Minister's Office (Mr Heng Chee How) | Mr Speaker, Sir, supplementary question. I would like to ask if the Minister would agree that there are also many employers out there who do appreciate the value of their older workers and what they bring to the job and the company. In last year's economy, for example, the employment rate for the older workers actually went up. The results for the unionised sector, for example, have also been very good.
10 |  | 820 | Mr Gan Kim Yong | Yes, I agree, Sir. In fact, in my reply earlier, I did mention that the employment rate for older workers in 2009, despite the recession, maintained at 57%. This is encouraging but it still requires us to continue to put in more effort to help prepare our workers for the re-employment which will come into effect by 2012.
"""

_REPORT_37237_TITLE = "PRIMARY SCHOOL LEAVING EXAMINATION IN 1967"
_REPORT_37237_ROWS = """
1 |  | 41 | Mr Ng Kah Ting | asked the Minister for Education whether all students who pass the Primary School Leaving Examination this year will be given places in secondary schools; whether he is aware of the many cases in previous years where students were posted to secondary schools far away from their homes; and what steps he will take to prevent a similar situation this year.
2 |  | 44 | Mr Ong Pang Boon | Mr Speaker. Sir, it is expected that, subject to adequate provision in the 1968 Budget for education, every Primary VI pupil in Singapore who is successful in the Primary School Leaving Examination this year will be given a place in a secondary academic, technical or vocational school. However, it is obviously not possible to meet the wishes of every parent in regard to the choice of a particular school. No system of allocation can please everyone.
3 |  | 44 | Mr Ong Pang Boon | The present system of allocation for the Chinese and English streams, which has been in operation since 1965, is processed by computers. It is based on the choice exercised by the parents and the results of the Primary School Leaving Examination. Under this system the vast majority of successful candidates are posted to schools of their own choice. For example, in 1966, out of a total of 32,602 successful candidates, 21,074 were posted to schools according to their first choice, and 6,036 were posted according to their second choice. Only 5,492 or 16.8 per cent were posted to schools other than their choice, because all vacancies in the schools of their choice were taken up by other candidates with better results in the Primary School Leaving Examination. Among the 5,492 pupils who failed to secure a place under their first as well as second choice, about 5,200 applied for transfers. Of these, 4,600 were approved and only 600 could not be approved, because all vacancies in schools near their homes had already been taken up by other pupils with better examination results.
4 |  | 41 | Mr Ng Kah Ting (Punggol) | Mr Speaker, Sir, just now the Minister has said that, subject to adequate provision in the 1968 Budget, it appears that all students who passed the Primary School Leaving Examination would be given places. Could the Minister be more explicit in explaining the phrase "subject to adequate provision in the 1968 Budget"?
5 |  | 44 | Mr Ong Pang Boon | Mr Speaker, Sir, I think the Member for Punggol knows exactly what I mean. There is no need to explain in further detail.
6 |  | 41 | Mr Ng Kah Ting | Can the Minister say whether it is correct that, should there be inadequate provision in the 1968 Budget, all students may not be given places in the secondary schools?
7 |  | 20 | The Minister for Finance (Dr Goh Keng Swee) | Correct.
8 |  | 44 | Mr Ong Pang Boon | The Minister for Finance has already answered for me.
"""

_REPORT_18267_TITLE = (
    "Students under Direct School Admission (DSA) Scheme who Drop Out of CCAs"
)
_REPORT_18267_ROWS = """
1 |  | 1012 | Mr Yee Jenn Jong | asked the Minister for Education, for Secondary schools that admit students under the Direct School Admission (DSA) scheme based on the students' achievements in Co-Curricular Activities (CCA) or sports (a) whether there are clear policies on how schools will handle students who drop out of their designated CCA or sports after admission; and (b) over the past three years, how many students admitted under the DSA scheme do not enrol in or have dropped out of their designated DSA activities within two years of admission.
2 |  | 935 | The Senior Parliamentary Secretary to the Minister for Education (Mr Hawazi Daipi) (for the Minister for Education) | Madam, the Direct School Admission (DSA) scheme was introduced in 2004 to give selected schools the flexibility and autonomy to recognise a more diverse range of student achievements and talents beyond performance at the national examinations. The intent is to promote holistic education by encouraging a broader definition of merit.
3 |  | 935 | The Senior Parliamentary Secretary to the Minister for Education (Mr Hawazi Daipi) (for the Minister for Education) | Generally, MOE expects that students admitted through DSA understand the commitment on their part to participate in the CCAs and activities related to the talent for which they were admitted. The intent is also for the DSA school to nurture these students further in their strengths. However, we also recognise that there might be a few cases where the DSA students may need to transfer out of their CCAs due to unforeseen reasons, for example, due to sports injury. In such cases, schools will work with the student on a change in CCA for the educational interests of the student.
4 |  | 935 | The Senior Parliamentary Secretary to the Minister for Education (Mr Hawazi Daipi) (for the Minister for Education) | Over the past three years and on average, of the students admitted through DSA, about 95% are still in a CCA related to their DSA talent two years after their admission.
5 |  | 1012 | Mr Yee Jenn Jong (Non-Constituency Member) | Thank you, Mdm Speaker. I would just like to seek an additional clarification. Earlier, in one of the replies to my question prior to this, the Ministry had said that the policy for what to do with students will depend on a school-to-school basis. I would like to know if the Ministry has a general consistent policy across the board because we are going to have more and more schools going into the DSA system and more and more students coming through DSA. So, would it be better to have a clearer communication across all schools?
6 |  | 1012 | Mr Yee Jenn Jong (Non-Constituency Member) | I also understand the explanation that, for example, if there is sports injury, then there would be a good reason for them to move to another activity. But what if the students have no good reasons and they just wish to drop the CCA? What would the Ministry advise schools to do in such circumstances?
7 |  | 935 | Mr Hawazi Daipi | I thank the Member for the questions. The principle of honouring one's commitment applies to both school transfers as well as CCA transfers. What we want to do is to have students commit themselves to the school that they have applied for under DSA. Where students have lost interest, the schools will counsel them. But, essentially, schools will take it case by case. As I have said earlier, 95% of the students remain in the CCA and in the school, undertaking CCAs for which they had been admitted to the schools, after two years. This means the system works. We want the students to honour their commitment to the school, having been admitted based on the specific DSA talent.
8 |  | 990 | The Minister of State for Education (Ms Sim Ann) | Mdm Speaker, Mr Yee earlier referred to a previous reply given by MOE to one of his questions. I do not know whether he is referring to the previous parliamentary sitting. If he is, perhaps he could give a nod because I do recall he asked a supplementary question, to a main question which I answered, which was with regards to DSA about students who may have been admitted through sports and about whether their PSLE scores have had a certain gap between the cut-off point of that particular school.
9 |  | 990 | The Minister of State for Education (Ms Sim Ann) | Mr Yee raised this issue about CCAs as a supplementary question and I recall the answer that I gave was not that it differs from school to school but that it would be looked at on a case-by-case basis. And I believe that the answer that my colleague the Senior Parliamentary Secretary Mr Hawazi Daipi has just given corroborates this.
"""


def test_report_37303_office_holders_quip_is_not_an_answer() -> None:
    labelled_report = _label_report(
        _REPORT_37303_TITLE,
        _REPORT_37303_ROWS,
        speaker_id_to_office={
            1: Office(
                "Parliamentary Secretary to the Minister for Education",
                OfficeSource.ATTENDANCE_LIST,
            ),
            64: Office("Minister for Health", OfficeSource.ATTENDANCE_LIST),
        },
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Madam Chan Choy Siong",
            9,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            2,
            "Inche Rahim Ishak (for the Minister for Education)",
            1,
        ),
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            3,
            "The Minister for Health (Mr Yong Nyuk Lin)",
            64,
        ),
    ]


def test_report_15769_office_holders_short_reply_to_the_chair_is_not_an_answer() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_15769_TITLE,
        _REPORT_15769_ROWS,
        speaker_id_to_office={
            1113: Office(
                "Minister of State for Manpower", OfficeSource.ATTENDANCE_LIST
            ),
            1039: Office(
                "Senior Minister of State for National Development",
                OfficeSource.ATTENDANCE_LIST,
            ),
        },
    )

    assert [
        participant
        for participant in _summarise_participants(labelled_report.participants)
        if participant[4] == _DESMOND_LEE_SPEAKER_ID
    ] == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            21,
            "The Senior Minister of State for National Development (Mr Desmond Lee)",
            1039,
        )
    ]


def test_report_21632_office_holder_who_asks_a_supplementary_is_a_supplementary() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_21632_TITLE,
        _REPORT_21632_ROWS,
        speaker_id_to_office={
            826: Office(
                "Minister of State, Prime Minister's Office",
                OfficeSource.ATTENDANCE_LIST,
            ),
            820: Office("Minister for Manpower", OfficeSource.ATTENDANCE_LIST),
        },
    )

    assert [
        participant
        for participant in _summarise_participants(labelled_report.participants)
        if participant[4] == _HENG_CHEE_HOW_SPEAKER_ID
    ] == [
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            9,
            "The Minister of State, Prime Minister's Office (Mr Heng Chee How)",
            826,
        )
    ]


def test_report_37237_office_holders_one_word_reply_is_an_answer() -> None:
    labelled_report = _label_report(
        _REPORT_37237_TITLE,
        _REPORT_37237_ROWS,
        speaker_id_to_office={
            44: Office("Minister for Education", OfficeSource.ATTENDANCE_LIST),
            20: Office("Minister for Finance", OfficeSource.ATTENDANCE_LIST),
        },
    )

    assert [
        participant
        for participant in _summarise_participants(labelled_report.participants)
        if participant[0] == ParticipantRole.ANSWERER
    ] == [
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            2,
            "Mr Ong Pang Boon",
            44,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            7,
            "The Minister for Finance (Dr Goh Keng Swee)",
            20,
        ),
    ]


def test_report_18267_office_holder_who_mentions_a_supplementary_question_is_an_answerer() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_18267_TITLE,
        _REPORT_18267_ROWS,
        speaker_id_to_office={
            935: Office(
                "Senior Parliamentary Secretary to the Minister for Education",
                OfficeSource.ATTENDANCE_LIST,
            ),
            990: Office(
                "Minister of State for Education", OfficeSource.ATTENDANCE_LIST
            ),
        },
    )

    assert [
        participant
        for participant in _summarise_participants(labelled_report.participants)
        if participant[4] == _SIM_ANN_SPEAKER_ID
    ] == [
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            8,
            "The Minister of State for Education (Ms Sim Ann)",
            990,
        )
    ]


_REPORT_6260_TITLE = "Affordability of Rising Public Housing Prices and Impact of Prices on Marriage and Fertility Rates"
_REPORT_6260_ROWS = """
1 |  | 1238 | Mr Yip Hon Weng | asked the Minister for National Development (a) what measures are being taken to address the growing sentiment that Singapore property market is unaffordable for the masses; (b) how will the recent adjustments to manpower policies impact property prices; and (c) beyond existing cooling measures, what else will the Government do to ensure housing remains affordable for Singaporeans if housing market conditions do not improve.
2 |  | 1205 | Ms Hazel Poa | asked the Minister for National Development whether the Ministry has conducted or will conduct studies on the impact of rising public housing prices on marriage and fertility rates.
3 |  | 1151 | The Minister for National Development (Mr Desmond Lee) | Mr Speaker, Sir, Question No 2 on today's Order Paper on the issue of marriage and parenthood is also relevant to this question on public housing affordability. As such, may I request, Sir, that the answers to Question Nos 1 and 2 be provided first, and the supplementary questions from Members on both questions be taken together thereafter.
4 |  | 1223 | Mr Speaker | Please proceed.
5 |  | 1151 | Mr Desmond Lee | Thank you, Sir. This reply will also respond to the Member's question for 3 October on affordability benchmarks for public housing.
"""


def test_report_6260_ministers_opening_line_is_not_a_read_out() -> None:
    labelled_report = _label_report(
        _REPORT_6260_TITLE,
        _REPORT_6260_ROWS,
        speaker_id_to_office={
            1151: Office(
                "Minister for National Development", OfficeSource.ATTENDANCE_LIST
            )
        },
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr Yip Hon Weng",
            1238,
        ),
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            2,
            "Ms Hazel Poa",
            1205,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            3,
            "The Minister for National Development (Mr Desmond Lee)",
            1151,
        ),
        (
            ParticipantRole.CHAIR,
            ParticipantRoleSource.CHAIR_LABEL,
            4,
            "Mr Speaker",
            1223,
        ),
    ]


_REPORT_32259_TITLE = "HDB FLATS AT POTONG PASIR ESTATE"
_REPORT_32259_ROWS = """
1 | SPEECH | 359 | Mr Chiam See Tong | asked the Minister for National Development (a) what were the values of successful awards for construction of Housing and Development Board flats at Potong Pasir New Town.
2 | SPEECH | 408 | Mr Teh Cheang Wan | Mr Deputy Speaker, Sir, the values of structural works on contracts 1 to 7 at Potong Pasir Estate are as follows:
3 | SPEECH | 403 | Mr Deputy Speaker | Mr Vasoo.
4 | SPEECH | 411 | Mr S. Vasoo (Bo Wen) | Mr Deputy Speaker, can I proceed with my question? Question No. 5, Sir.
5 | SPEECH | 403 | Mr Deputy Speaker | I am sorry. We are proceeding to Question No. 5 already.
"""


def test_report_32259_member_who_calls_the_next_question_mid_paragraph_is_unlabelled() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_32259_TITLE,
        _REPORT_32259_ROWS,
        speaker_id_to_office={
            408: Office(
                "Minister for National Development", OfficeSource.HEADER_IN_REPORT
            )
        },
    )

    assert [
        participant
        for participant in _summarise_participants(labelled_report.participants)
        if participant[4] == _VASOO_SPEAKER_ID
    ] == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            4,
            "Mr S. Vasoo (Bo Wen)",
            411,
        )
    ]


_REPORT_2577_ROWS = """
1 | SPEECH | 1199 | Mr Louis Ng Kok Kwang | asked the Minister for National Development whether he can provide an update on the testing undertaken by the Ministry of a prototype.
2 | SPEECH | 1199 | Mr Louis Ng Kok Kwang (Nee Soon) | Question No 10, please.
3 | SPEECH | 1213 | Mr Speaker | Anyone from the Ministry of National Development? There is none. Let me move on to the next Parliamentary Question then.
"""
_REPORT_52005_ROWS = """
1 | SPEECH | 1321 | Ms Poh Li San | asked the Coordinating Minister for Social Policies and Minister for Health how will the Ministry further collaborate with the Coalition for Epidemic Preparedness Innovations.
2 | SPEECH | 1327 | Mr Speaker | Order. Questions for oral answer.
3 | SPEECH | 1321 | Ms Poh Li San (Sembawang West) | Question No 1.
4 | SPEECH | 1327 | Mr Speaker | Who is answering for Question No 1? [_Please refer to the Official Report, 7 October 2026._]
5 | SPEECH | 1327 | Mr Speaker | Let me move on. I believe the first two questions are for the same Ministry.
"""
_REPORT_46417_ROWS = """
1 | SPEECH | 1134 | Mr Ang Wei Neng | asked the Prime Minister whether the National Wages Council has completed its review on the wage guidelines for the coming year.
2 | SPEECH | 1134 | Mr Ang Wei Neng (West Coast) | Question No 4, Sir.
3 | SPEECH | 1144 | Mr Deputy Speaker | Perhaps, Mr Ang, if you could give way, I will call Parliamentary Question No 5.
4 | SPEECH | 1134 | Mr Ang Wei Neng | Yes, Sir.
"""
_REPORT_38002_ROWS = """
1 | SPEECH | 2 | Mr Speaker | Inche Mohd. Ariff.
2 | SPEECH | 40 | Inche Mohd. Ariff Bin Suradi | I am not asking Question No. 26, Sir.
3 | SPEECH | 40 | Inche Mohd. Ariff Bin Suradi | [The following is Question No. 26:-
4 | SPEECH | 40 | Inche Mohd. Ariff Bin Suradi | To ask the Minister for Law and National Development whether he is aware that all the unpaved drains in the Kampong Kembangan area have been neglected for more than a year.]
"""
_REPORT_36405_ROWS = """
1 | SPEECH | 127 | Mr Speaker | Mr Ng Yeow Chong.
2 | SPEECH | 102 | Mr Ng Yeow Chong (Mountbatten) | Sir, I am not asking the Question.
3 | SPEECH | 102 | Mr Ng Yeow Chong (Mountbatten) | [The following is Question No. 1:
4 | SPEECH | 102 | Mr Ng Yeow Chong (Mountbatten) | To ask the Minister for Law and National Development if he is aware that some dispossessed families are subject to clearance action for the second time after having been rehoused.
"""
_REPORT_38897_ROWS = """
1 | UNCLASSIFIED |  |  | The following question stood in the name of Mr David Marshall -
2 | DOCUMENT_TEXT |  |  | * To ask the Minister for Finance what are the consumption figures of petroleum for the years 1961 and 1960.
3 | SPEECH | 1352 | Mr Speaker | Mr Marshall, Question No. 2*.
4 | SPEECH | 1349 | Mr David Marshall | I have since ascertained the information I sought in Question No. 2*, Mr Speaker. I do not ask it.
"""
_REPORT_39958_ROWS = """
1 | SPEECH | 1358 | Inche Ahmad Bin Ibrahim | asked the Minister for Education how many primary and secondary school students were asked to line the route taken by the Duke of Edinburgh.
2 | SPEECH | 1352 | Mr Speaker | The Minister appears to be absent.
"""
_REPORT_39096_ROWS = """
1 | UNCLASSIFIED |  |  | The following Question stood in the name of Mr David Marshall:-
2 | DOCUMENT_TEXT |  |  | 1. To ask the Prime Minister what is the title of the Singapore Government to the land and installations involved in the Scudai River scheme.
3 | SPEECH | 1352 | Mr Speaker | Order. There is one question in the name of the Member for Anson. He does not appear to be here. I take it the Minister responsible will be submitting a written reply in due course.
"""


@pytest.mark.parametrize(
    ("rows_text", "line_ordinal"),
    [
        pytest.param(_REPORT_2577_ROWS, 3, id="2577"),
        pytest.param(_REPORT_52005_ROWS, 4, id="52005"),
        pytest.param(_REPORT_46417_ROWS, 3, id="46417"),
        pytest.param(_REPORT_38002_ROWS, 2, id="38002"),
        pytest.param(_REPORT_36405_ROWS, 2, id="36405"),
        pytest.param(_REPORT_38897_ROWS, 4, id="38897"),
        pytest.param(_REPORT_39958_ROWS, 2, id="39958"),
        pytest.param(_REPORT_39096_ROWS, 3, id="39096"),
    ],
)
def test_question_the_record_says_was_not_asked_aloud_gets_the_state(
    rows_text: str, line_ordinal: int
) -> None:
    printed_line = next(
        speech_asker_row
        for speech_asker_row in _parse_rows(rows_text)
        if speech_asker_row.ordinal == line_ordinal
    )

    labelled_report = _label_report(
        "A question",
        rows_text,
        printed_name_to_speaker_id={"Mr David Marshall": 1349},
    )

    assert _summarise_states(labelled_report.states) == [
        (QuestionState.NOT_ASKED_ALOUD, printed_line.transcript, line_ordinal)
    ]


_REPORT_26319_TITLE = "Households paying quit rent"
_REPORT_26319_ROWS = """
1 | SPEECH | 619 | Mr Charles Chong | asked the Minister for Law what percentage of households in Singapore are required to pay quit rent and whether his Ministry will review the need to impose quit rent.
2 | SPEECH | 619 | Mr Charles Chong | Prof. S. Jayakumar:
3 | SPEECH | 619 | Mr Charles Chong | Currently, 2,705 households pay quit rent.
"""
_REPORT_37816_TITLE = "Postage rates"
_REPORT_37816_ROWS = """
1 | SPEECH | 37 | Mr S. V. Lingam | asked the Deputy Prime Minister whether he will consider revising the postage for local letters to the pre-Malaysia rate. i.e. ten cents.
2 | SPEECH | 37 | Mr S. V. Lingam | Dr Toh Chin Chye : The postage rate on inland letters in Malaysia was raised from 10 cents to 15 cents as from 16th November, 1964 by the Government of Malaysia for the following reasons:
"""
_REPORT_30635_TITLE = "Public perception of Total Defence"
_REPORT_30635_ROWS = """
1 | SPEECH | 477 | Dr Ong Chit Chung | asked the First Deputy Prime Minister and Minister for Defence what is his assessment of the public perception and support for Total Defence.
2 | SPEECH | 477 | Dr Ong Chit Chung | The Second Minister for Defence (Policy)(Dr Yeo Ning Hong)(for the First Deputy Prime Minister and Minister for Defence): Mr Speaker, Sir, the concept of Total Defence was introduced in 1984.
"""


@pytest.mark.parametrize(
    ("title", "rows_text", "inline_label", "speaker_id", "role_source"),
    [
        pytest.param(
            _REPORT_26319_TITLE,
            _REPORT_26319_ROWS,
            "Prof. S. Jayakumar",
            1,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            id="26319",
        ),
        pytest.param(
            _REPORT_37816_TITLE,
            _REPORT_37816_ROWS,
            "Dr Toh Chin Chye",
            2,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            id="37816",
        ),
        pytest.param(
            _REPORT_30635_TITLE,
            _REPORT_30635_ROWS,
            "The Second Minister for Defence (Policy)(Dr Yeo Ning Hong)(for the First Deputy Prime Minister and Minister for Defence)",
            3,
            ParticipantRoleSource.OFFICE_LABEL,
            id="30635",
        ),
    ],
)
def test_answer_printed_under_the_askers_label_with_the_name_inline_gives_the_answerer(
    title: str,
    rows_text: str,
    inline_label: str,
    speaker_id: int,
    role_source: ParticipantRoleSource,
) -> None:
    labelled_report = _label_report(
        title,
        rows_text,
        speaker_id_to_office={
            speaker_id: Office("Minister for Law", OfficeSource.ATTENDANCE_LIST)
        },
        inline_label_to_speaker_id={inline_label: speaker_id},
    )

    assert [
        (participant.role, participant.role_source, participant.printed_name)
        for participant in labelled_report.participants
        if participant.role == ParticipantRole.ANSWERER
    ] == [(ParticipantRole.ANSWERER, role_source, inline_label)]


_REPORT_38206_TITLE = "ADDENDUM - PERUMAL AND SIVAN TEMPLES"
_REPORT_38206_ROWS = """
1 | DOCUMENT_TEXT |  |  | ADDENDUM PERUMAL AND SIVAN TEMPLES
2 | DOCUMENT_TEXT |  |  | Inche Othman bin Wok, with reference to his replies to the following two supplementary questions on 10th June, 1964 (Official Report, 10th June, 1964, Vol. 23, No. 1, Columns 9 and 10):
3 | DOCUMENT_TEXT |  |  | supplied the following additional answers on 2nd October, 1964:
"""
_REPORT_39437_TITLE = (
    "VACANT POSTS IN GOVERNMENT SERVICE HELD BY OFFICERS IN ACTING CAPACITY"
)
_REPORT_39437_ROWS = """
1 | DOCUMENT_TEXT |  |  | ADDENDA VACANT POSTS IN GOVERNMENT SERVICE HELD BY OFFICERS IN ACTING CAPACITY
2 | DOCUMENT_TEXT |  |  | Dr Goh Keng Swee, pursuant to his reply to the following question for oral answer asked on 21st September, 1960 (Official Report, 21st September, 1960, Volume 13, No. 9, column 624):
3 | DOCUMENT_TEXT |  |  | supplied the following answer on 8th November, 1960:
"""
_REPORT_40924_TITLE = "DAILY DIGEST OF NON-ENGLISH PRESS"
_REPORT_40924_ROWS = """
1 | SPEECH | 1404 | Mr W. A. C. Goode, | pursuant to his reply to the following question for oral answer asked on 13th February, 1957 (Official Report, 13th February, 1957, Volume 2, No. 19, Column 1393):
2 | SPEECH | 1404 | Mr W. A. C. Goode, | Mr David Marshall asked the Chief Secretary whether he will make available to the English-reading public of Singapore by public subscription the Information Services' Daily Digest of Non-English Press,
3 | SPEECH | 1404 | Mr W. A. C. Goode, | supplied the following answer on 5th March, 1957:-
"""
_REPORT_32219_TITLE = "25 YEARS OF NATION BUILDING"
_REPORT_32219_ROWS = """
1 | DOCUMENT_TEXT |  |  | 25 YEARS OF NATION BUILDING (Cost of celebrations)
2 | DOCUMENT_TEXT |  |  | Consequent on the Question raised by Mr J.B. Jeyaretnam on
3 | DOCUMENT_TEXT |  |  | 14 May 1985, the Second Deputy Prime Minister supplied the following information on 22 July 1985 on the final cost of celebrations to the tax payer:
"""


@pytest.mark.parametrize(
    ("title", "rows_text", "printed_ordinal"),
    [
        pytest.param(_REPORT_38206_TITLE, _REPORT_38206_ROWS, None, id="38206"),
        pytest.param(_REPORT_39437_TITLE, _REPORT_39437_ROWS, 3, id="39437"),
        pytest.param(_REPORT_40924_TITLE, _REPORT_40924_ROWS, 3, id="40924"),
        pytest.param(_REPORT_32219_TITLE, _REPORT_32219_ROWS, 3, id="32219"),
    ],
)
def test_addendum_or_later_supplied_answer_is_a_correction_not_a_non_question(
    title: str, rows_text: str, printed_ordinal: Optional[int]
) -> None:
    printed_text = (
        title
        if printed_ordinal is None
        else next(
            speech_asker_row.transcript
            for speech_asker_row in _parse_rows(rows_text)
            if speech_asker_row.ordinal == printed_ordinal
        )
    )

    labelled_report = _label_report(title, rows_text)

    assert _summarise_states(labelled_report.states) == [
        (QuestionState.CORRECTION, printed_text, printed_ordinal)
    ]


_REPORT_11641_TITLE = "Support for Singaporean workers"
_REPORT_11641_ROWS = """
1 | SPEECH | 1037 | Mr Dennis Tan Lip Fong | asked the Minister for Manpower what support is available for retrenched workers.
2 | SPEECH | 408 | Mr Teh Cheang Wan | Mr Speaker, Sir, support is available through several schemes.
3 | SPEECH | 1038 | Mr Dennis Tan Lip Fong (Non-Constituency Member) | Mr Speaker, Sir, I am not sure I have heard the Senior Minister of State answering Question No 5. Could I ask him to answer Question No 5 again?
4 | SPEECH | 411 | Mr S. Vasoo (Bo Wen) | I think there might be a Question No 10 before my question, Mdm Speaker.
"""


def test_report_11641_member_who_only_mentions_a_question_number_stays_supplementary() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_11641_TITLE,
        _REPORT_11641_ROWS,
        speaker_id_to_office={
            408: Office("Minister for Manpower", OfficeSource.HEADER_IN_REPORT)
        },
    )

    assert [
        participant[0]
        for participant in _summarise_participants(labelled_report.participants)
        if participant[4] in (1038, _VASOO_SPEAKER_ID)
    ] == [ParticipantRole.SUPPLEMENTARY, ParticipantRole.SUPPLEMENTARY]


_REPORT_37970_TITLE = "PENG CHEE HIGH SCHOOL"
_REPORT_37970_ROWS = """
1 | UNCLASSIFIED |  |  | The following Question for Oral Answer stood on the Order Paper of 20th December, 1965 :-
2 | SPEECH | 46 | Mr Poh Ber Liak | To ask the Minister for Education whether the Government intends to give any assistance to Peng Ghee High School for development, and if he will give details."
3 | SPEECH | 46 | Mr Poh Ber Liak | Pursuant to Standing Order No. 20 (2), the Minister for Education supplied the following answer:-
"""


def test_report_37970_answer_supplied_under_a_standing_order_is_no_correction() -> None:
    labelled_report = _label_report(_REPORT_37970_TITLE, _REPORT_37970_ROWS)

    assert QuestionState.CORRECTION not in [
        question_state[0]
        for question_state in _summarise_states(labelled_report.states)
    ]


def test_report_26319_paragraph_after_an_inline_answer_belongs_to_the_inline_speaker() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_26319_TITLE,
        _REPORT_26319_ROWS,
        speaker_id_to_office={
            637: Office("Minister for Law", OfficeSource.ATTENDANCE_LIST)
        },
        inline_label_to_speaker_id={"Prof. S. Jayakumar": 637},
    )

    assert [
        participant.role
        for participant in labelled_report.participants
        if participant.speaker_id == _CHARLES_CHONG_SPEAKER_ID
    ] == [ParticipantRole.ASKER]


_REPORT_27568_TITLE = "IMPACT OF REGIONAL CURRENCY CRISIS ON THE ECONOMY"
_REPORT_27568_ROWS = """
1 | SPEECH | 681 | Mr Tay Beng Chuan | asked the Minister for Trade and Industry if he will give an assessment of the impact of the regional currency and financial crisis on Singapore's economy.
2 | SPEECH | 620 | Mr Choo Wee Khiang | Question No. 11, Sir.
3 | SPEECH | 646 | Mr Lee Yock Suan | Mr Speaker, Sir, may I answer Question Nos. 11 and 12 together as they are related?
4 | SPEECH | 679 | Mr Speaker | Yes.
5 | SPEECH | 646 | Mr Lee Yock Suan | As the Singapore economy is closely linked to the region, it will inevitably be affected if the regional currency crisis continues for a prolonged period.
"""


def test_report_27568_filer_of_an_asked_row_whose_question_is_read_out_is_an_absent_filer() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_27568_TITLE,
        _REPORT_27568_ROWS,
        speaker_id_to_office={
            646: Office("Minister for Trade and Industry", OfficeSource.ATTENDANCE_LIST)
        },
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ABSENT_FILER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr Tay Beng Chuan",
            681,
        ),
        (
            ParticipantRole.READER,
            ParticipantRoleSource.ASKER_RULES,
            2,
            "Mr Choo Wee Khiang",
            620,
        ),
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            3,
            "Mr Lee Yock Suan",
            646,
        ),
        (
            ParticipantRole.CHAIR,
            ParticipantRoleSource.CHAIR_LABEL,
            4,
            "Mr Speaker",
            679,
        ),
    ]
    assert _summarise_states(labelled_report.states) == []


_REPORT_20093_TITLE = "UNLICENSED TOUR GUIDES IN SINGAPORE"
_REPORT_20093_ROWS = """
1 | SPEECH | 916 | Mrs Lina Chiam | –
2 | SPEECH | 916 | Mrs Lina Chiam | 11To ask the Minister for Trade and Industry (a) what is the number of unlicensed tour guides caught during the last five years
3 | SPEECH | 430 | Dr Lily Neo (Tanjong Pagar) | Question No 11, Sir.
4 | SPEECH | 700 | Mr Lee Yi Shyan | Mr Speaker, Sir, the number of unlicensed tour guides caught was 61 over the last five years.
"""


def test_report_20093_filer_of_a_to_ask_row_whose_question_is_read_out_is_an_absent_filer() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_20093_TITLE,
        _REPORT_20093_ROWS,
        speaker_id_to_office={
            700: Office(
                "Minister of State for Trade and Industry", OfficeSource.ATTENDANCE_LIST
            )
        },
    )

    assert [
        (participant.role, participant.speaker_id)
        for participant in labelled_report.participants
    ] == [
        (ParticipantRole.ABSENT_FILER, 916),
        (ParticipantRole.READER, 430),
        (ParticipantRole.ANSWERER, 700),
    ]


_REPORT_47504_TITLE = "Increase in Fake Bulk Order Scams Impersonating SAF Personnel and Measures to Protect Small Businesses"
_REPORT_47504_ROWS = """
1 | SPEECH | 1287 | Mr Jackson Lam | asked the Coordinating Minister for National Security and Minister for Home Affairs (a) how many cases of fake bulk order scams impersonating SAF personnel have been reported since May 2025
2 | SPEECH | 1279 | The Minister of State for Home Affairs (Mr Goh Pei Ming) (the Coordinating Minister for National Security and Minister for Home Affairs) | Mr Speaker, my reply will also address Question Nos 10 and 12 for written answer in today’s Order Paper filed by Mr Alex Yeo and Mr Zhulkarnain Adbul Rahim respectively.
3 | SPEECH | 1279 | The Minister of State for Home Affairs (Mr Goh Pei Ming) (the Coordinating Minister for National Security and Minister for Home Affairs) | From May 2025 to 15 September 2025, the Police received at least six reports of fake bulk order scams.
4 | SPEECH | 1279 | The Minister of State for Home Affairs (Mr Goh Pei Ming) (the Coordinating Minister for National Security and Minister for Home Affairs) | Please note also that Government agencies will not ask businesses to make payment to another business on the Government’s behalf.
5 | SPEECH | 1327 | Mr Speaker | Mr Lam.
6 | SPEECH | 1287 | Mr Jackson Lam (Nee Soon) | I thank the Minister of State for his reply. Can I ask whether the Ministry of Home Affairs is working with other agencies to develop verification tools?
7 | SPEECH | 1279 | Mr Goh Pei Ming | Mr Speaker, I thank the Member for the supplementary question.
8 | SPEECH | 1327 | Mr Speaker | Mr Alex Yeo.
9 | SPEECH | 1243 | Mr Alex Yeo (Potong Pasir) | Mr Speaker, I thank the Minister of State for his answer to the Parliamentary Question. Can I just ask a supplementary question to the Minister of State?
10 | SPEECH | 1279 | Mr Goh Pei Ming | Mr Speaker, I thank the Member for the question.
"""


def test_report_47504_member_whose_own_question_the_minister_folds_into_the_reply_is_supplementary() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_47504_TITLE,
        _REPORT_47504_ROWS,
        printed_name_to_speaker_id={"Mr Jackson Lam": 1287},
        speaker_id_to_office={
            1279: Office(
                "Minister of State for Home Affairs", OfficeSource.ATTENDANCE_LIST
            )
        },
    )

    assert [
        (participant.role, participant.speaker_id)
        for participant in labelled_report.participants
    ] == [
        (ParticipantRole.ASKER, 1287),
        (ParticipantRole.ANSWERER, 1279),
        (ParticipantRole.CHAIR, 1327),
        (ParticipantRole.ASKER_FOLLOW_UP, 1287),
        (ParticipantRole.SUPPLEMENTARY, 1243),
    ]


_REPORT_30972_TITLE = "REVISION OF PUBLIC ASSISTANCE RATES"
_REPORT_30972_ROWS = """
1 | UNCLASSIFIED |  |  | The following question stood in the name of Mr Teo Chong Tee -
2 | DOCUMENT_TEXT |  |  | 9. To ask the Minister for Community Development whether the public assistance rates wll be revised upwards.
3 | SPEECH | 409 | Mr Teo Chong Tee | Mr Speaker, Sir, for Question No. 9, the Minister has given the answer yesterday. I therefore withdraw the question.
"""


def test_report_30972_stood_filer_who_speaks_stays_an_absent_filer() -> None:
    labelled_report = _label_report(
        _REPORT_30972_TITLE,
        _REPORT_30972_ROWS,
        printed_name_to_speaker_id={"Mr Teo Chong Tee": 409},
    )

    assert _summarise_participants(labelled_report.participants) == [
        (
            ParticipantRole.ABSENT_FILER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr Teo Chong Tee",
            409,
        )
    ]


_REPORT_40823_TITLE = "REDUCED RENTS FOR NEW S.I.T. FLATS"
_REPORT_40823_ROWS = """
1 | SPEECH | 1397 | Mr Lim Choon Mong | asked the Minister for Local Government, Lands, and Housing whether he will consider taking steps to have the proposed rents of $30/$35 per month for the new Singapore Improvement Trust flats in the Albert Street, Prinsep Street and Short Street area reduced at least to
2 | SPEECH | 1372 | Inche Abdul Hamid | Mr Speaker, Sir, the reply is no. The White Paper on housing subsidy policy gives the method of subsidising public housing which the Government is following. In the case of flats now being built under S.I.T. Programme No. 8 for rentals of $30/$35 per month,
3 | SPEECH | 1397 | Mr Lim Choon Mong | Mr Speaker, Sir, is the Minister aware that some private builders are offering houses which are three times the size of the present flats at about $100 per month?
4 | SPEECH | 1354 | Mr Chew Swee Kee | Quote facts.
"""
_REPORT_37381_TITLE = "PEOPLE'S DEFENCE FORCE (WOMEN) AND POLICE FORCE (WOMEN)"
_REPORT_37381_ROWS = """
1 | SPEECH | 9 | Madam Chan Choy Siong | asked the Minister of Defence whether he is satisfied with the overall performances of the People's Defence Force (Women) and the Police Force (Women) at the National Day March Past, and whether he intends to increase and expand both Units.
2 | SPEECH | 60 | Mr Wee Toon Boon (for the Minister of Defence) | Mr Speaker. Sir, the Minister was very satisfied with the People's Defence Force (Women) on their outstanding performance at the National Day March Past. There are no immediate plans to expand this unit.
3 | SPEECH | 60 | Mr Wee Toon Boon (for the Minister of Defence) | The Police Force (Women) did not participate in the National Day March Past. This was due to their numerous rehearsals in connection with the Police Military Display, which was another highlight of National Day Celebrations. There are no plans to increase this component of the
4 | SPEECH | 9 | Madam Chan Choy Siong (Delta) | I would like the Minister of State to clarify whether those women soldiers who took part in the National Day March Past were holding real rifles or fake ones, because many people, especially the male population, tend to say that women soldiers are not capable
5 | SPEECH | 60 | Mr Wee Toon Boon | Mr Speaker, Sir, the weapons carried by the women P.D.F, on the National Day Parade were, of course, real ones and serviceable. In fact, many of the women P.D.F, have used them. However, as the Member for Delta has raised this point, I would like
6 | CHAMBER_EVENT |  |  | Madam Chan Choy Siong rose -
7 | SPEECH | 16 | Mr Speaker | Please make sure, Madam Chan, that it arises out of your original question and answer and not the Minister of State's second answer.
8 | SPEECH | 9 | Madam Chan Choy Siong | Does the Minister agree that the People's Defence Force (Women) has been admired and appreciated by the Ministers, because it is said that the male members of the Force were sleepy on that day when they were marching along the road?
9 | SPEECH | 60 | Mr Wee Toon Boon | That was the first time that the women P.D.F, participated in the National Day Parade and no doubt they put up a very smart march past. But to be fair to everyone, I would not dare to say that they were the best among the
10 | SPEECH | 45 | The Minister for Culture and Social Affairs (Inche Othman Bin Wok) | I think the men did the best on that day, Sir!
11 | SPEECH | 16 | Mr Speaker | Order. We must not allow domestic squabbles to come into the House.
"""
_REPORT_38170_TITLE = "ELECTRICITY SUPPLY IN PUNGGOL"
_REPORT_38170_ROWS = """
1 | SPEECH | 41 | Mr Ng Kah Ting | asked the Minister for National Development whether and when electricity will be supplied from 9 milestone Punggol Road to Punggol Point.
2 | SPEECH | 23 | The Parliamentary Secretary to the Minister for National Development (Mr Ho Cheng Choon) | Mr Speaker, Sir, I answer on behalf of my Minister.
3 | SPEECH | 2 | Mr Speaker | Will the hon. Member please resume his seat?
4 | CHAMBER_EVENT |  |  | Mr Ho Cheng Choon resumed his seat.
5 | SPEECH | 35 | Mr Lim Kim San | Mr Speaker, Sir, if it is in order, my Parliamentary Secretary will reply on my behalf.
6 | SPEECH | 2 | Mr Speaker | Mr Ho Cheng Choon, please proceed.
7 | SPEECH | 23 | Mr Ho Cheng Choon | The Urban and Rural Services Consultative Committee has drawn up a scheme for the supply of electricity by the Public Utilities Board to the whole of Punggol area. The scheme covers the following areas:
8 | SPEECH | 23 | Mr Ho Cheng Choon | Lorong Buang Kok
9 | SPEECH | 23 | Mr Ho Cheng Choon | Kampong Sungei Tengah
10 | SPEECH | 23 | Mr Ho Cheng Choon | Jalan Kampong Tengah
11 | SPEECH | 23 | Mr Ho Cheng Choon | Kampong Serangoon Kechil, and
12 | SPEECH | 23 | Mr Ho Cheng Choon | Punggol Road, 9¾ m.s. to seafront.
13 | SPEECH | 23 | Mr Ho Cheng Choon | Some of these areas have already been supplied with electricity. The stretch of Punggol Road from 9¾ m.s. to the sea-front will be supplied with electricity as soon as the sub-station in constructed. Action has already been taken by the Public Utilities Board to acquire
14 | SPEECH | 41 | Mr Ng Kah Ting | What is the total cost of this electrification scheme and is there any subsidy granted by the Government?
15 | SPEECH | 23 | Mr Ho Cheng Choon | The total cost of this scheme will be $272,190. The revenue over a period of seven years from the areas benefitting is estimated to be about $255,484 and a subsidy of $16,000, or $42 per house, has been paid by the Government to enable the
"""
_REPORT_16254_TITLE = "Effectiveness of Support Schemes in Helping PMETs Find New Jobs"
_REPORT_16254_ROWS = """
1 | SPEECH | 1045 | Ms Foo Mee Har | asked the Minister for Manpower in light of job layoffs hitting a seven-year high (a) how successful have current support schemes been in helping Singaporeans, particularly PMEs, secure new jobs; and (b) what additional measures will the Government implement should the unemployment situation deteriorate further.
2 | SPEECH | 1079 | The Minister for Manpower (Mr Lim Swee Say) | Mdm Speaker, redundancies have risen due to weaker global economic conditions and ongoing economic restructuring. In anticipation of this, I announced in April this year the "Adapt and Grow" initiative.
3 | SPEECH | 1079 | The Minister for Manpower (Mr Lim Swee Say) | Under "Adapt and Grow", we have enhanced and expanded the package of employment assistance for both the affected professionals, managers, executives and technicians (PMETs) and rank-and-file workers. It includes the Professional Conversion Programme, Career Support Programme, P-Max and Reskilling for Jobs Programme. The Workforce Development
4 | SPEECH | 1079 | The Minister for Manpower (Mr Lim Swee Say) | Ms Foo Mee Har asked how effective our current support schemes are. Mdm Speaker, in the first half of this year, WDA and e2i have assisted about 15,000 jobseekers through its Career Centres and the Adapt and Grow support programmes. With WDA and e2i assistance,
5 | SPEECH | 1079 | The Minister for Manpower (Mr Lim Swee Say) | Ms Foo also asked what additional measures we will implement moving forward. Mdm Speaker, the Government will continue to monitor the economic and labour market situation closely and expand employment support to our workers proactively as we go through this period of not just cyclical
6 | SPEECH | 1079 | The Minister for Manpower (Mr Lim Swee Say) | Moving forward, with the restructuring of WDA into the Workforce Singapore (WSG), we will go beyond helping the unemployed find jobs. WSG will do more and help more Singaporeans manage their career transitions throughout life. This is to maximise matching between the aspiration of workers
7 | SPEECH | 1052 | Mdm Speaker | Ms Foo Mee Har. Keep your question short. Yes, Mr Low Thia Khiang.
8 | SPEECH | 1081 | Mr Low Thia Khiang (Aljunied) | Mdm Speaker, earlier on, I had a supplementary question to ask from Minister Shanmugam's answer.
9 | SPEECH | 1052 | Mdm Speaker | Mr Low, we have already past that question.
10 | SPEECH | 1081 | Mr Low Thia Khiang | Mdm Speaker, I regret that. I should have been allowed to ask more supplementary questions.
11 | SPEECH | 1052 | Mdm Speaker | You should have put your hand up very quickly, Mr Low. Unfortunately, I have already called the next question. Ms Foo, make it very short and snappy.
12 | SPEECH | 1063 | The Minister for Home Affairs (Mr K Shanmugam) | Mdm Speaker, if there is any process for allowing Mr Low to ask a question, I am happy to take the question. But I leave that entirely to you.
13 | SPEECH | 1052 | Mdm Speaker | Minister, we have already past the Parliamentary Question (PQ) and we have already moved on to the next PQ. So, Ms Foo, please make it fast.
14 | SPEECH | 1045 | Ms Foo Mee Har (West Coast) | Yes, Madam. I would like to ask the Minister with respect to the double weak companies – those with weak Singaporean Core and a weak commitment to nurture a Singaporean Core – would the Minister please give an update on how these companies have strengthened
15 | SPEECH | 1079 | Mr Lim Swee Say | Mdm Speaker, indeed, we have taken action against not just the double weak but triple weak companies as well. These are companies that are weak in Singaporean Core today, weak in their commitment to strengthen the Singaporean Core in the future, as well as weak
16 | SPEECH | 1052 | Mdm Speaker | Order. End of Question Time.
17 | EDITORIAL_NOTE |  |  | [_Pursuant to Standing Order No 22(3), provided that Members had not asked for questions standing in their names to be postponed to a later Sitting day or withdrawn, written answers to questions not reached by the end of Question Time are reproduced in the Appendix._]
"""
_REPORT_39076_TITLE = "ORAL ANSWER TO QUESTION"
_REPORT_39076_ROWS = """
1 | SPEECH | 1352 | Mr Speaker | Question. Mr Marshall.
2 | SPEECH | 1349 | Mr David Marshall (Anson) | Question No. 1+, Mr Speaker, Sir.
3 | EDITORIAL_NOTE |  |  | + The Question reads as follows:-
4 | EDITORIAL_NOTE |  |  | To ask the Prime Minister whether the statement made by him over Radio Singapore on the 10th October, 1961, to the effect that if an expatriate lawyer, when pursuing his professional responsibilities, says or does something which is considered foolish and is considered to injure
5 | SPEECH | 30 | The Prime Minister (Mr Lee Kuan Yew) | not being in his seat -
6 | SPEECH | 1352 | Mr Speaker | The Prime Minister is not here.
7 | CHAMBER_EVENT |  |  | The Deputy Prime Minister (Dr Toh Chin Chye) rose -
8 | SPEECH | 1352 | Mr Speaker | Dr Toh.
9 | SPEECH | 59 | Dr Toh Chin Chye | Just in elucidation of this, Sir. I am not supposed to answer this question. The question has been directed at the Prime Minister. I just wish to apologise on his behalf to the House that he is not here at the moment to answer it.
10 | SPEECH | 1352 | Mr Speaker | The relevant Standing Order is Standing Order 20, paragraph (3), which reads:
11 | SPEECH | 1352 | Mr Speaker | 'If a Minister, Parliamentary Secretary or other Member, who is to answer a question, is absent, the question shall, if he then be present, be taken after all other questions appearing on the Order Paper has been disposed of. If the Minister, Parliamentary Secretary or
12 | SPEECH | 1352 | Mr Speaker | Therefore, the Prime Minister's answer will have to be circulated in the ordinary way.
13 | SPEECH | 1349 | Mr David Marshall | On a point of elucidation, Sir. Would it be permissible if the Prime Minister were to make a statement instead of circulating the reply, so that we could ask supplementaries?
14 | SPEECH | 1352 | Mr Speaker | Certainly. If the Prime Minister thinks fit, at the appropriate time tomorrow, he could make a ministerial statement.
15 | SPEECH | 59 | Dr Toh Chin Chye | I am quite sure he will be quite prepared.
"""


def _get_person_rows(
    labelled_report: _LabelledReport, speaker_id: int
) -> list[tuple[ParticipantRole, ParticipantRoleSource, int, str, Optional[int]]]:
    return [
        participant
        for participant in _summarise_participants(labelled_report.participants)
        if participant[4] == speaker_id
    ]


def test_report_40823_later_holders_two_word_remark_is_not_an_answer() -> None:
    labelled_report = _label_report(
        _REPORT_40823_TITLE,
        _REPORT_40823_ROWS,
        speaker_id_to_office={
            1372: Office(
                "Parliamentary Secretary to the Minister for Local Government, Lands and Housing",
                OfficeSource.ATTENDANCE_LIST,
            ),
            1354: Office("Minister for Education", OfficeSource.ATTENDANCE_LIST),
        },
    )

    assert _get_person_rows(labelled_report, 1354) == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            4,
            "Mr Chew Swee Kee",
            1354,
        )
    ]


def test_report_37381_later_holders_ten_word_quip_is_not_an_answer() -> None:
    labelled_report = _label_report(
        _REPORT_37381_TITLE,
        _REPORT_37381_ROWS,
        speaker_id_to_office={
            60: Office("Minister of State of Defence", OfficeSource.HEADER_IN_REPORT)
        },
    )

    assert _get_person_rows(labelled_report, 45) == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            10,
            "The Minister for Culture and Social Affairs (Inche Othman Bin Wok)",
            45,
        )
    ]


def test_report_38170_later_holder_who_says_the_secretary_will_reply_on_my_behalf_is_not_answering() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_38170_TITLE,
        _REPORT_38170_ROWS,
        speaker_id_to_office={
            35: Office(
                "Minister for National Development", OfficeSource.HEADER_IN_REPORT
            )
        },
    )

    assert _get_person_rows(labelled_report, 35) == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            5,
            "Mr Lim Kim San",
            35,
        )
    ]


def test_report_16254_later_holder_who_leaves_it_entirely_to_the_chair_is_not_answering() -> (
    None
):
    labelled_report = _label_report(_REPORT_16254_TITLE, _REPORT_16254_ROWS)

    assert _get_person_rows(labelled_report, 1063) == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            12,
            "The Minister for Home Affairs (Mr K Shanmugam)",
            1063,
        )
    ]


def test_report_39076_later_holder_who_is_not_supposed_to_answer_is_not_answering() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_39076_TITLE,
        _REPORT_39076_ROWS,
        printed_name_to_speaker_id={"Mr Marshall": 1349},
        speaker_id_to_office={
            59: Office(
                "Deputy Prime Minister and Leader of the House",
                OfficeSource.HEADER_IN_REPORT,
            )
        },
    )

    assert _get_person_rows(labelled_report, 59) == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            9,
            "Dr Toh Chin Chye",
            59,
        )
    ]


_REPORT_38510_TITLE = "SEMBAWANG BY-ELECTION"
_REPORT_38510_ROWS = """
1 | SPEECH | 1349 | Mr David Marshall | asked the Prime Minister whether he has any further statement to make as to when it is proposed to hold a by-election for the Electoral Division of Sembawang.
2 | SPEECH | 30 | The Prime Minister | Mr Speaker, Sir, the Statistics Department is working at full capacity to complete the election registers by the end of this month, or the beginning of next. As I said at the last sitting, the Sembawang by-election will be held soon thereafter.
3 | SPEECH | 1349 | Mr David Marshall | Mr Speaker, Sir, if I remember right, we were assured at the last sitting that the by-election would take place within two months. May I ask the Prime Minister whether we can expect that by-election next month?
4 | SPEECH | 30 | The Prime Minister | First, I challenge the statement that the Member for Anson has attributed to me. You will notice that even when my Secretary writes to Amnesty International, he writes in very circumspect language.
5 | SPEECH | 1349 | Mr David Marshall | Dictated by you.
6 | SPEECH | 30 | The Prime Minister | I hope he has in his association with me learned how to deal with difficult gentlemen who ask difficult questions. I would assure the Member for Anson that however insidious he can be, he would never find me committed in writing in this Assembly or outside to
7 | SPEECH | 20 | The Minister for Finance (Dr Goh Keng Swee) | High-speed sorting machines.
8 | SPEECH | 30 | The Prime Minister | We have loaned from the City Council two high-speed sorting machines to the Statistics Department to discharge these functions more efficaciously. And my answer stands.
"""
_REPORT_38893_TITLE = "REPRESENTATIONS FROM GOVERNMENT EMPLOYEES"
_REPORT_38893_ROWS = """
1 | SPEECH | 1349 | Mr David Marshall | asked the Minister for Finance (a) whether he has received any representations from the Singapore Federation of Unions of Government Employees requesting a secret ballot among all Government employees other than teachers, senior officers and daily-rated person
2 | SPEECH | 20 | Dr Goh Keng Swee | Mr Speaker, Sir, a secret ballot of employees is usually taken where an employer refuses to accept an invitation to negotiate on grounds that he does not recognise the union. Where there are two or more unions claiming representation for the same group of empl
3 | SPEECH | 1349 | Mr David Marshall | Sir, would the Minister agree that rivalry between these two unions for membership of Government employees is unhealthy? For the unification of the trade union movement in the civil service, does he not consider it appropriate to accede to the request of the F
4 | SPEECH | 20 | Dr Goh Keng Swee | Mr Speaker, Sir, there is rivalry not only between unions affiliated to the Federation, hut also between member unions of the Federation themselves. For instance, a stenographer employed in the Broadcasting Division of the Ministry of Culture is eligible for m
5 | SPEECH | 1349 | Mr David Marshall | If it please you, Mr Speaker, could I have a reply to my question? It is this: Does the Minister not consider that it would be helpful to the unification of the trade union movement in the civil service if he were to accede to the request of the Federation for
6 | SPEECH | 20 | Dr Goh Keng Swee | I do not think a secret ballot will solve anything. One of the requests of the Federation is that if they should win the secret ballot, then they ask the Government to require the A.U.P.E. to amend its rules so that they would not be able to recruit Government
7 | SPEECH | 30 | The Prime Minister | The problem only rises when we refuse recognition.
8 | SPEECH | 20 | Dr Goh Keng Swee | The problem arises only, when as I have mentioned before, we refuse recognition to a particular union.
"""
_REPORT_38737_TITLE = "APPLICATION OF LABOUR ORDINANCE TO DOMESTIC SERVANTS"
_REPORT_38737_ROWS = """
1 | SPEECH | 1349 | Mr David Marshall | asked the Minister for Labour whether Government will consider applying the Labour Ordinance to domestic servants.
2 | SPEECH | 60 | The Parliamentary Secretary to the Minister for Labour (Mr Wee Toon Boon) (for the Minister for Labour) | Mr Speaker, Sir, I am asked to reply. This matter has been receiving attention for a considerable time in view of the need to be sure that no unrealistic or impracticable measures are introduced whose immediate effect would be to deprive thousands of these wor
3 | SPEECH | 1349 | Mr David Marshall | Mr Speaker, Sir, as I understand the circumlocution, there is no intention of applying the Ordinance to domestic servants. But would the Par liamentary Secretary consider at least issuing regulations for guidance of good employer relations in respect of domest
4 | SPEECH | 30 | The Prime Minister | Come, come, Mr Marshall.
5 | SPEECH | 60 | Mr Wee Toon Boon | Mr Speaker, Sir, in that respect, the Member for Anson can rest assured that though employers arc not obliged to give certain benefits to the employees under this Ordinance, but nevertheless when domestic employees are aggrieved because they are not given suff
6 | SPEECH | 30 | The Prime Minister | Or otherwise maltreated.
7 | SPEECH | 60 | Mr Wee Toon Boon | - maltreated they always consult and seek the assistance of the Labour Ministry. We have always assisted them in getting sufficient compensation or adequate notice of termination of their service.
8 | SPEECH | 1349 | Mr David Marshall | I had in mind rather the question of whether the Government would assist employers to recognise the limitation of hours and conditions of work, and if it does not wish to apply the provisions whether it would issue some regulations for guidance.
9 | SPEECH | 60 | Mr Wee Toon Boon | Mr Speaker, Sir, domestic servants are different from factory workers. Therefore, it has to be left to the conscience of the employers to impose fair working conditions on their domestic servants. I hope that the Member for Anson will set the example.
"""


def test_report_38510_later_holders_short_reply_the_first_answerer_takes_up_is_an_answer() -> (
    None
):
    labelled_report = _label_report(_REPORT_38510_TITLE, _REPORT_38510_ROWS)

    assert _get_person_rows(labelled_report, 20) == [
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            7,
            "The Minister for Finance (Dr Goh Keng Swee)",
            20,
        )
    ]


def test_report_38893_later_holders_short_reply_the_first_answerer_restates_is_an_answer() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_38893_TITLE,
        _REPORT_38893_ROWS,
        speaker_id_to_office={
            20: Office("Minister for Finance", OfficeSource.HEADER_IN_REPORT)
        },
    )

    assert _get_person_rows(labelled_report, 30) == [
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            7,
            "The Prime Minister",
            30,
        )
    ]


def test_report_38737_later_holders_interjection_the_first_answerer_only_partly_repeats_is_not_an_answer() -> (
    None
):
    labelled_report = _label_report(_REPORT_38737_TITLE, _REPORT_38737_ROWS)

    assert _get_person_rows(labelled_report, 30) == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            4,
            "The Prime Minister",
            30,
        )
    ]


_REPORT_33240_TITLE = "MR PHEY YEW KOK"
_REPORT_33240_ROWS = """
1 | UNCLASSIFIED |  |  | olumn: 376
2 | SPEECH | 301 | Mr J.B. Jeyaretnam | asked the Minister for Home Affairs whether he will outline all steps that have been taken to obtain or secure the return to this country of Mr Phey Yew Kok former President of the National Trades Union Congress to stand trial upon the charges instit
3 | SPEECH | 288 | The Minister for Home Affairs (Mr Chua Sian Chin) | Mr Speaker, Sir, Phey Yew Kok was charged in court on 10th December, 1979 on four counts of criminal breach of trust (CBT) and two counts under the Trade Unions Act. He was allowed bail. When the case was brought up for mention on 7th January, 1980,
4 | SPEECH | 288 | The Minister for Home Affairs (Mr Chua Sian Chin) | Phey Yew Kok was required to call at the Corrupt Practices Investigation Bureau (CPIB) on 2nd January, 1980. When he failed to do so, CPIB officers visited his house and spoke to his wife. She claimed that she did not know where he was. At the same t
5 | SPEECH | 288 | The Minister for Home Affairs (Mr Chua Sian Chin) | Subsequent investigations carried out by CPIB revealed that Phey Yew Kok had left Singapore for Kuala Lumpur by train on 31st December, 1979. From there he went to Bangkok where he disappeared. CPIB had contacted the Thai Police authorities for assis
6 | SPEECH | 288 | The Minister for Home Affairs (Mr Chua Sian Chin) | Immediately after he jumped bail, a warrant for his arrest was issued. CPIB also made an immediate appeal in the local newspapers for information on Phey Yew Kok's whereabouts.
7 | SPEECH | 288 | The Minister for Home Affairs (Mr Chua Sian Chin) | Interpol Headquarters was alerted and it notified all Interpol countries to arrest Phey Yew Kok. Should he be arrested in a country which has an extradition treaty with Singapore, his extradition will be sought.
8 | SPEECH | 288 | The Minister for Home Affairs (Mr Chua Sian Chin) | The Immigration Department also cancelled both his International Passport and his Restricted Passport for travel to West Malaysia. All Immigration checkpoints have been told to seize his passport and refer him to CPIB if he were to pass through any c
9 | SPEECH | 288 | The Minister for Home Affairs (Mr Chua Sian Chin) | His present whereabouts are unknown.
10 | SPEECH | 288 | The Minister for Home Affairs (Mr Chua Sian Chin) | When Phey Yew Kok eventually returns to Singapore, as he must if he wants to be with his wife and family again, he will have to face the charges against him. Each day he remains a fugitive, is a day of punishment, without it being considered part of
11 | SPEECH | 301 | Mr Jeyaretnam | Mr Speaker, Sir, the Minister has said that it was an error of judgment in not taking away Mr Phey Yew Kok's passport. Would the Minister say whose error of judgment it was and whether he had asked for any explanation from this man who made the error
12 | SPEECH | 288 | Mr Chua Sian Chin | Mr Speaker, Sir, as a lawyer, the Member for Anson should know that it is not as of right that you can ask for the retention of a passport of a person who has been granted bail. It is a matter for the discretion of the Court whether to allow retentio
13 | SPEECH | 288 | Mr Chua Sian Chin | As to the specific question whether the police officer concerned has made an error of judgment, yes, he has made an error of judgment. Of course, in his opinion it was unlikely that a person of Mr Phey's position would jump bail. It is not something
14 | SPEECH | 329 | Mr Sia Khoon Seong (Moulmein) | Mr Speaker, Sir, I do not know whether my supplementary question should be directed to the Minister or to the Member for Anson, but is it not right to say that there had been others who jumped bail even when their passports had been seized? In other
15 | SPEECH | 288 | Mr Chua Sian Chin | Mr Speaker, Sir, the answer is yes, there are also other means by which a person can jump bail even without a passport.
16 | SPEECH | 329 | Mr Sia Khoon Seong | Mr Speaker, Sir, with the benefit of hindsight, it can now be said that there has been an error of judgment. But could I ask the Minister, or perhaps the Member for Anson, that without the benefit of hindsight, was it not quite natural for the office
17 | SPEECH | 322 | The Second Deputy Prime Minister (Foreign Affairs) (Mr S. Rajaratnam) | I can think of one!
18 | SPEECH | 288 | Mr Chua Sian Chin | Mr Speaker, Sir, we do not go around punishing police officers for making an error of judgment. We only punish them if there is negligence on their part. I can assure the Member that there was no negligence on his part, civil or criminal negligence.
19 | SPEECH | 301 | Mr Jeyaretnam | Sir, is the Minister not aware that the first thing that the CPIB officers do is to impound passports of persons into whose crimes they are inquiring? I know this, Mr Speaker, from the cases that I have handled, that the first thing the CPIB do is to
20 | SPEECH | 288 | Mr Chua Sian Chin | Mr Speaker, Sir, before I answer that question I want a clarification from the Member for Anson. What does he mean by saying that before the officer decided not to impound the pass- port of Phey Yew Kok, did he ask for directions from the DPP? As a l
21 | SPEECH | 301 | Mr Jeyaretnam | May I answer that question, Sir?
22 | SPEECH | 347 | Mr Speaker | Yes, Mr Jeyaretnam.
23 | SPEECH | 301 | Mr Jeyaretnam | The Minister talks about impounding of passports after completion of investigations. Mr Phey Yew Kok was produced in court. I should have thought that all investigations were completed by the time he was produced in court. Why was there not an applic
24 | SPEECH | 322 | Mr Rajaratnam | A point of clarification, Sir. I am not speaking from any experience. In view of the sneaky proposal that the Member put earlier to the Prime Minister that the charges against Phey Yew Kok should be dropped, is he really serious in pursuing this particular question?
25 | SPEECH | 288 | Mr Chua Sian Chin | Now the Member's question is clear, and that is whether the officer did ask for directions to impound or not to impound the passport of Phey Yew Kok after he was charged in court. The answer is: yes, he did. The point is this. As I have said just now
26 | SPEECH | 301 | Mr Jeyaretnam | Mr Speaker, Sir, the Minister has said that the officer did ask for directions. May we know who he asked for directions from?
27 | SPEECH | 288 | Mr Chua Sian Chin | He asked directions from the DPP.
"""
_REPORT_32427_TITLE = "SOCIAL DEVELOPMENT UNIT"
_REPORT_32427_ROWS = """
1 | SPEECH | 375 | Mr J.B. Jeyaretnam | asked the Minister for Finance, Minister for Education and Minister for Health if he will state how much of the tax-payers' monies has been spent by the Social
2 | SPEECH | 402 | The Minister for Finance, Minister for Education and Minister for Health (Dr Tony Tan Keng Yam) | Mr Speaker, Sir, the total amount that has been spent by the Social Development Unit on its activities as at 15th February, 1985, was $294,411.72.
3 | SPEECH | 402 | The Minister for Finance, Minister for Education and Minister for Health (Dr Tony Tan Keng Yam) | The Unit's objectives are long-term:
4 | SPEECH | 402 | The Minister for Finance, Minister for Education and Minister for Health (Dr Tony Tan Keng Yam) | (i) To create an awareness of the problem of the high incidence of singlehood among our graduate women; and
5 | SPEECH | 402 | The Minister for Finance, Minister for Education and Minister for Health (Dr Tony Tan Keng Yam) | (ii) To bring about a change of attitude towards marriage in our younger single officers.
6 | SPEECH | 402 | The Minister for Finance, Minister for Education and Minister for Health (Dr Tony Tan Keng Yam) | Some progress has been made towards these objectives. More single officers are participating in the activities organized by the Unit. These officers are prepare
7 | SPEECH | 402 | The Minister for Finance, Minister for Education and Minister for Health (Dr Tony Tan Keng Yam) | The single officers are also more open in discussing marriage and their choice of partners. Through attending the activities organized by the Social Development
8 | SPEECH | 375 | Mr J.B. Jeyaretnam (Anson) | Mr Speaker, Sir, my first supplementary question for the Minister is: was parliamentary approval obtained for this expenditure of $294,411.72? I have tried to l
9 | SPEECH | 402 | Dr Tony Tan Keng Yam | Mr Speaker, Sir, I see no necessity to obtain specific parliamentary approval for this expenditure.
10 | SPEECH | 375 | Mr Jeyaretnam | Does the Minister not accept that every expenditure should be laid before Parliament?
11 | SPEECH | 402 | Dr Tony Tan Keng Yam | Mr Speaker, Sir, the expenditure of the Government is spelt out in the Government's Budget which I shall be presenting on Friday. On that occasion, the Member f
12 | SPEECH | 375 | Mr Jeyaretnam | My question to the Hon. Minister was: does he not accept that every expenditure of the Government must be laid before Parliament? My question, I repeat, is: doe
13 | SPEECH | 402 | Dr Tony Tan Keng Yam | Mr Speaker, Sir, I have already explained that the Government does not indulge in expenditure which is not within its authorized limits and which has not been a
14 | SPEECH | 375 | Mr Jeyaretnam | Mr Speaker, Sir, another supplementary question. I see that the Minister is not going to answer my earlier question. Notwithstanding that, I have another questi
15 | SPEECH | 402 | Dr Tony Tan Keng Yam | Mr Speaker, Sir, the activities which have been organized for the participants of the Social Development Unit are of many types. They include, for example, pers
16 | SPEECH | 375 | Mr Jeyaretnam | I understood the Minister to say that the costs borne by these participants vary from 15% to 100%. Is he now saying that all those who go on cruises or on holid
17 | SPEECH | 402 | Dr Tony Tan Keng Yam | All those who go on cruises bear the full cost. All those who go on courses organized by the Social Development Unit bear a substantial part of the cost, but wh
18 | SPEECH | 375 | Mr Jeyaretnam | I asked for results. Would the Hon. Minister say how many graduates have married from the time the Social Development Unit began its functions?
19 | SPEECH | 402 | Dr Tony Tan Keng Yam | Sir, the Unit has only been in operation since the beginning of last year. I know that in Singapore we are an impatient society but love must take time to bloom
20 | SPEECH | 375 | Mr Jeyaretnam | I see that the Hon. Minister is reporting a nil result although the Unit has been functioning, as I understand, from January 1984.
21 | SPEECH | 375 | Mr Jeyaretnam | May I ask the Hon. Minister whether the then First Deputy Prime Minister was speaking for the Government when he said at a car park on Nomination Day that if th
22 | SPEECH | 366 | The First Deputy Prime Minister and Minister for Defence (Mr Goh Chok Tong) | On a point of clarification, Mr Speaker, Sir. Could the Member please let me know the exact quotation and where was the statement made?
23 | SPEECH | 375 | Mr Jeyaretnam | Mr Speaker, Sir, this was certainly reported in the Straits Times on the day after Nomination Day, and it was headlined "Dr Goh Keng Swee's press conference in
24 | SPEECH | 402 | Dr Tony Tan Keng Yam | Mr Speaker, Sir, there seems to be a confusion between the two Gohs in Parliament - one past and one present. Notwithstanding that, you cannot force people to m
25 | SPEECH | 402 | Dr Tony Tan Keng Yam | The reason why the SDU's activities have been, for the time being, limited to graduates is because that is where the problem is. Non-graduates seem to get along
26 | SPEECH | 399 | Dr Augustine H.H. Tan (Whampoa) | A supplementary question, Mr Speaker, Sir. Since our graduate men seem to be much in demand both by graduate ladies and non-graduates, should not the Government
27 | SPEECH | 402 | Dr Tony Tan Keng Yam | Mr Speaker, Sir, I shall convey that excellent suggestion from the Member for Whampoa to the Social Development Unit's Director.
28 | SPEECH | 374 | Mr Jek Yeun Thong (Queenstown) | A supplementary question, Sir. I know it is a misfortune for the Minister to have to answer this question. But since he is paid to answer it, and I am paid to a
29 | SPEECH | 402 | Dr Tony Tan Keng Yam | Mr Speaker, Sir, I would first inform the Member for Queenstown that it is not a hardship but a pleasure to answer his question. By all means, feel free to ask
30 | SPEECH | 402 | Dr Tony Tan Keng Yam | He has quoted a Chinese proverb. The equivalent of that is the English proverb, "You can bring a horse to the water but you cannot make him drink", if he does n
31 | SPEECH | 402 | Dr Tony Tan Keng Yam | From time to time I see on television various attempts in China and in America to try and get pandas to mate. They put a male panda and a female panda together,
32 | SPEECH | 399 | Dr Augustine Tan | Supplementary question, Mr Speaker, Sir. I know that the Government has got honourable intentions in this matter but what precautions have been taken by the Soc
33 | SPEECH | 402 | Dr Tony Tan Keng Yam | Sir, I strongly resent the allegation from the Member for Whampoa. The Director of the SDU is a most upright Christian, with extremely high moral values. Such a
34 | SPEECH | 403 | Mr Tan Soo Khoon (Alexandra) | Supplementary question, Sir. After listening to the Minister, I wish I had waited a bit longer! Now that the Government has entered the marriage broking busines
35 | SPEECH | 402 | Dr Tony Tan Keng Yam | Mr Speaker, Sir, Members of Parliament should be very careful before they say anything. I think the Member would have a difficult time when he goes home tonight
36 | CHAMBER_EVENT |  |  | [Laughter]
37 | SPEECH | 402 | Dr Tony Tan Keng Yam | But to be more serious, if private companies would take on some of the activities of the SDU, if they would do so, then I can see that nothing but good can come
38 | SPEECH | 375 | Mr Jeyaretnam | Would the Minister please answer my question? I have been very patient with the Minister. My question was, if I may repeat it: was the then First Deputy Prime M
39 | SPEECH | 402 | Dr Tony Tan Keng Yam | Mr Speaker, Sir, the answer is very simple: I do not propose to take any further measures.
"""
_REPORT_32411_TITLE = "RESETTLEMENT OF STREET HAWKERS"
_REPORT_32411_ROWS = """
1 | SPEECH | 389 | Mr Ng Kah Ting | asked the Minister for the Environment how many street hawkers have been resettled into the hawker centres since the introduction Qf the policy to ensure better
2 | SPEECH | 381 | Dr Lee Boon Yang (for the Minister for the Environment) | Sir, in May 1971, the Government decided to build markets and food centres to accommodate all the street hawkers. There were then about 17,800 hawkers on the st
3 | SPEECH | 381 | Dr Lee Boon Yang (for the Minister for the Environment) | Today, some 17,300 of these hawkers have been relocated into markets and food centres. There are now only 546 street hawkers. They will be housed by the end of
4 | SPEECH | 381 | Dr Lee Boon Yang (for the Minister for the Environment) | There are a total of 25,448 food and market produce stalls housed mainly in centres managed by HDB, MOE, and other statutory boards. 1,525 of the market produce
5 | SPEECH | 381 | Dr Lee Boon Yang (for the Minister for the Environment) | Sir, the Ministry of the Environment has no plans to build any more food centres, as the relocation programme is nearing completion. We have barely over 500 mor
6 | SPEECH | 381 | Dr Lee Boon Yang (for the Minister for the Environment) | Sir, Singaporeans have a wide variety of food outlets to suit their taste and budget. There are 192 food centres with some 9,069 foodstalls, 1,508 eating houses
7 | SPEECH | 381 | Dr Lee Boon Yang (for the Minister for the Environment) | Apart from those provided by HDB as part of its amenities for housing estates, the private sectors can also set up food centres and eating establishments to cat
8 | SPEECH | 389 | Mr Ng Kah Ting | Mr Speaker, Sir, does the Parliamentary Secretary to the Minister for Communications and Information and the Minister for the Environment not realize that the a
9 | SPEECH | 381 | Dr Lee Boon Yang | Mr Speaker, Sir, the Government, in particular my Ministry, is aware that more and more people are eating outside their home. This has to be so, as we encourage
10 | SPEECH | 389 | Mr Ng Kah Ting | Mr Speaker, Sir, just one final supplementary question. Does not the Parliamentary Secretary agree with me that all this means additional expenditure, resulting
11 | SPEECH | 381 | Dr Lee Boon Yang | Mr Speaker, Sir, there may be some increase in costs but the quality of service is increased to justify this increase in cost. The more important thing is that
12 | SPEECH | 375 | Mr Jeyaretnam | Mr Speaker, Sir, may I ask a supplementary question, although not on food and hawker centres? Did I understand the Parliamentary Secretary to say that his Minis
13 | SPEECH | 381 | Dr Lee Boon Yang | Mr Speaker, Sir, the Member for Anson has been in this House longer than 1. He was in this House on 14 March 1984 when my predecessor, the hon. Member for Chang
14 | SPEECH | 381 | Dr Lee Boon Yang | 'In 1981, a study team chaired by the former Senior Parliamentary Secretary of my Ministry and comprising Members of Parliament and officials from the Ministry
15 | SPEECH | 375 | Mr Jeyaretnam | I am afraid the Parliamentary Secretary has not answered my question, The question is, "Was a survey taken from the residents?" I know you read out the recommen
16 | SPEECH | 373 | The Minister for Home Affairs and Second Minister for Law (Prof S. Jayakumar) | On a point of order, Mr Speaker, Sir. Ought not the Member for Anson ask this question at the time the previous statement was made?
17 | SPEECH | 375 | Mr Jeyaretnam | May I not ask the question now? May I know?
18 | SPEECH | 396 | The Minister for Foreign Affairs and Minister for Community Development (Mr S. Dhanabalan) | Mr Speaker, Sir, on a point of order. It is not relevant to the original question that was asked in the Order Paper.
19 | SPEECH | 424 | Mr Speaker | He said this question is not relevant to the question on the Order Paper.
20 | SPEECH | 375 | Mr Jeyaretnam | But we are talking about the policy of the Ministry of the Environment.
21 | SPEECH | 424 | Mr Speaker | I allow you to carry on. Now you can carry on.
22 | SPEECH | 375 | Mr Jeyaretnam | Thank you, Sir. Would the Parliamentary Secretary answer this question?
23 | SPEECH | 381 | Dr Lee Boon Yang | Mr Speaker, Sir, the Committee in 1981 made a thorough assessment of all forms of retail - food retail, cooked food retail, market produce retail, and after exh
24 | SPEECH | 381 | Dr Lee Boon Yang | The other point that I want to remind the Member for Anson is that a wet market entails a high cost in terms of manpower. A very large number of people is requi
25 | SPEECH | 381 | Dr Lee Boon Yang | The other point, Mr Speaker, Sir, which I would like to remind the Member for Anson is that we have in the past built many wet markets, and at the present momen
26 | SPEECH | 375 | Mr Jeyaretnam | You still have not answered my question.
27 | SPEECH | 424 | Mr Speaker | The Leader of the House wishes to move a business motion.
"""
_REPORT_33323_TITLE = "ADMISSION TO SCHOOLS"
_REPORT_33323_ROWS = """
1 | SPEECH | 332 | Dr Tan Cheng Bock | asked the First Deputy Prime Minister and Minister of Education why priority is given to the 3rd child, who has an elder brother or sister studying in the schoo
2 | SPEECH | 336 | The Minister of State of Education (Dr Tay Eng Soon) (for the First Deputy Prime Minister and Minister of Education) | Mr Deputy Speaker, Sir, Phase 1 registration is for a second or third child who has an elder brother or sister studying in the same school. The reasons for this
3 | SPEECH | 336 | The Minister of State of Education (Dr Tay Eng Soon) (for the First Deputy Prime Minister and Minister of Education) | Phase 2 registration is more extensive. It includes, among others, children of parents who have direct connections with the school; parents, brothers or sisters
4 | SPEECH | 336 | The Minister of State of Education (Dr Tay Eng Soon) (for the First Deputy Prime Minister and Minister of Education) | I do not know how the hon. Member has been led to believe that sterilized parents have been promised priority by the Ministry over third child siblings whose pa
5 | SPEECH | 336 | The Minister of State of Education (Dr Tay Eng Soon) (for the First Deputy Prime Minister and Minister of Education) | The matter raised by the hon. Member is academic. Since 1977, the number of children of parents sterilized after the birth of the first or second child varied b
6 | SPEECH | 332 | Dr Tan Cheng Bock (Ayer Rajah) | Mr Deputy Speaker, Sir, before I ask my supplementary question, I would just like to enlighten the House on the family planning programme of our nation.
7 | SPEECH | 298 | Mr Deputy Speaker | Dr Tan, will you please keep it brief because we have quite a few questions today?
8 | SPEECH | 332 | Dr Tan Cheng Bock | Yes. Mr Deputy Speaker, Sir, I would like to draw the attention of this House to the Family Planning and Population Board which was established by an Act of Par
9 | SPEECH | 298 | Mr Deputy Speaker | Dr Tan, what is your supplementary question?
10 | SPEECH | 332 | Dr Tan Cheng Bock | Sir, I think I need to explain before I come to the supplementary question. I think you must allow me to continue, Sir.
11 | SPEECH | 298 | Mr Deputy Speaker | Yes.
12 | SPEECH | 332 | Dr Tan Cheng Bock | Thank you very much. These policies were further intensified in 1972. These include, among others, higher priority for choice primary schools for children, one
13 | SPEECH | 332 | Dr Tan Cheng Bock | In line with our national policy in 1975, a total of 9,495 women were sterilized. 16% of those who ligated did so after one or two children, Why did I choose 19
14 | SPEECH | 293 | The First Deputy Prime Minister and Minister of Education (Dr Goh Keng Swee) | Point of order, Sir. Is the hon. Member delivering a speech or asking a supplementary question?
15 | SPEECH | 298 | Mr Deputy Speaker | I have asked the Member for his supplementary question. Dr Tan, please let us have your supplementary question. If you cannot make up your mind, I will have to
16 | SPEECH | 332 | Dr Tan Cheng Bock | Sir, if you stop me at this stage, it is not very fair. I think I must continue further.
17 | SPEECH | 298 | Mr Deputy Speaker | Then get on with your point, please.
18 | SPEECH | 332 | Dr Tan Cheng Bock | What I want to point out is that we must not give Singaporeans the impression that we -
19 | SPEECH | 293 | Dr Goh Keng Swee | Mr Deputy Speaker, Sir, I must insist that the hon. Member complies with Standing Orders. This is Question Time. I want to know what his supplementary question
20 | SPEECH | 298 | Mr Deputy Speaker | Dr Tan, let us have your supplementary question. If not, I have to call on Mr Ho for Question 2.
21 | SPEECH | 332 | Dr Tan Cheng Bock | My question is whether the Ministry of Education has taken into account the family planning policy of our nation. The Minister of State has said that the Minist
22 | SPEECH | 336 | Dr Tay Eng Soon | Mr Deputy Speaker, Sir, I have already said that those parents who were sterilized after one or two children have the highest priority under Phase 2 at any scho
23 | SPEECH | 336 | Dr Tay Eng Soon | This was the same understanding which the Ministry announced in 1974. I refer the hon. Member to the Straits Times of 22nd July 1974 in which we said that if on
"""


def test_report_33240_point_of_clarification_that_ends_in_a_question_is_supplementary() -> (
    None
):
    labelled_report = _label_report(_REPORT_33240_TITLE, _REPORT_33240_ROWS)

    assert _get_person_rows(labelled_report, 322) == [
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            17,
            "The Second Deputy Prime Minister (Foreign Affairs) (Mr S. Rajaratnam)",
            322,
        )
    ]


def test_report_32427_question_put_to_the_member_is_supplementary() -> None:
    labelled_report = _label_report(_REPORT_32427_TITLE, _REPORT_32427_ROWS)

    assert _get_person_rows(labelled_report, 366) == [
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            22,
            "The First Deputy Prime Minister and Minister for Defence (Mr Goh Chok Tong)",
            366,
        )
    ]


def test_report_32411_points_of_order_that_end_in_a_question_stay_unlabelled() -> None:
    labelled_report = _label_report(
        _REPORT_32411_TITLE,
        _REPORT_32411_ROWS,
        speaker_id_to_office={
            381: Office(
                "Parliamentary Secretary to the Minister for Communications and Information and Parliamentary Secretary to the Minister for the Environment",
                OfficeSource.HEADER_IN_REPORT,
            )
        },
    )

    assert _get_person_rows(labelled_report, 373) == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            16,
            "The Minister for Home Affairs and Second Minister for Law (Prof S. Jayakumar)",
            373,
        )
    ]
    assert _get_person_rows(labelled_report, 396) == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            18,
            "The Minister for Foreign Affairs and Minister for Community Development (Mr S. Dhanabalan)",
            396,
        )
    ]


def test_report_33323_point_of_order_that_ends_in_a_question_stays_unlabelled() -> None:
    labelled_report = _label_report(_REPORT_33323_TITLE, _REPORT_33323_ROWS)

    assert _get_person_rows(labelled_report, 293) == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            14,
            "The First Deputy Prime Minister and Minister of Education (Dr Goh Keng Swee)",
            293,
        )
    ]


_REPORT_20882_TITLE = "Holistic Approach to Education"
_REPORT_20882_ROWS = """
1 | SPEECH | 918 | Mr Christopher de Souza | asked the Minister for Education (a) whether the Ministry aims to have schoolgoing children enjoy their education and derive happiness from their pursuit of kno
2 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | Mr Speaker, Sir, Mr de Souza and the Ministry of Education share a common goal – to nurture each child holistically and to be the best that he can be. We want t
3 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | We, too, want our children to be happy, but this happiness must be derived from something deeper, the satisfaction of having worked hard, to master the skills a
4 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | How do we achieve it? I had outlined the key factors in my speech at the MOE Workplan Seminar in September. I signalled a clear emphasis on students’ centricity
5 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | Now, more than at any time in our history, we face unprecedented change. The more the world around us shifts and tilts, the more we need to be firmly anchored t
6 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | We have increased curriculum time for PE by between half an hour to an hour across all levels. We have put in place new programmes such as the Programmes for Ac
7 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | Second, we need to create the right condition for primary school to be a good school so that every child gets a positive school experience. It is worthwhile for
8 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | Anyone who has been watching the education scene will know that schools are seeking to do just that and introducing different types of programmes that meet dive
9 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | MOE has also created new pathways and options for students. Primary school students no longer get streamed but have a choice of Standard or Foundational subject
10 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | School attendance is universal, dropout rates are low, the quality of students experience in schools is rising and nine in 10 get into post-secondary educationa
11 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | Third, schools cannot do their important work alone. We need parents and the wider community to agree with us on the importance of developing each child holisti
12 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | We also need our parents to help their children discover their strengths, develop these and feel confident about what they are to become. At the same time, we h
13 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | Almost as soon as they landed in MOE, my colleagues, SPS Hawazi Daipi and SPS Sim Ann who are the Chair and Deputy Chair of the Community and Parents in Support
14 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | In my first few months in MOE, my team and I had spent much time meeting students, educators, school leaders and parents. The Government Parliamentary Committee
15 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | In the meantime, as one follow-up on my workplan seminar speech, MOE is working with schools to enhance our current guidelines on homework policy. When done wel
16 | SPEECH | 937 | The Minister for Education (Mr Heng Swee Keat) | Singaporeans invest a lot of hope and aspirations for a better society through our collective investment in our young. This is a precious asset. The support of
17 | SPEECH | 918 | Mr Christopher de Souza | First, I would like to thank the Minister and all his teachers for their vision to create a nurturing life-giving and confidence-giving environment in our schoo
18 | SPEECH | 937 | Mr Heng Swee Keat | Mr Speaker, Sir, I am glad that Mr de Souza was such a keen sportsman and had all the opportunities to play sports. Indeed, I agree with him. First, let me say
19 | SPEECH | 920 | Ms Denise Phua Lay Peng (Moulmein-Kallang) | Sir, I want to thank the Minister for his very comprehensive reply and also to compliment him for the wisdom to lead in the right direction, for example, in inc
20 | SPEECH | 937 | Mr Heng Swee Keat | I thank Ms Denise Phua for the question. In the subject of high-stake examinations and stress, I fully empathise with the parents and students. I know that many
21 | SPEECH | 937 | Mr Heng Swee Keat | First, the reason why we put the focus on student-centric holistic education is to recognise that each student is different, has different strengths and therefo
22 | SPEECH | 937 | Mr Heng Swee Keat | There will be more places at the universities, more pathways which the Minister of State Lawrence Wong is currently reviewing. To reduce some of these high-stak
23 | SPEECH | 937 | Mr Heng Swee Keat | Let me also say that the parents whom I have met and the feedback that had been given is that nobody has suggested abolishing examinations. Examinations well do
24 | SPEECH | 937 | Mr Heng Swee Keat | When I was in Japan a few months back, I looked at what Japan was doing. They had, because of the stress in the system, also reduced the curriculum content a fe
25 | SPEECH | 937 | Mr Heng Swee Keat | I also had many interactions with my counterparts from the advanced countries, seeking to learn from them but they were seeking to learn from us. They asked me
26 | SPEECH | 937 | Mr Heng Swee Keat | Let me end by saying that education is a long-term endeavour and whatever changes we make, let us recognise that we have a high quality, strong system. Whatever
27 | SPEECH | 983 | Mr Speaker | Mr Yee Jenn Jong, last question.
28 | SPEECH | 1012 | Mr Yee Jenn Jong (Non-Constituency Member) | Thank you to the Minister for clarifying. I would like to ask the Minister what he thinks of allowing students to take more than two CCAs if they so wish and if
29 | SPEECH | 937 | Mr Heng Swee Keat | Sir, I thank Mr Yee for that question. First, the Member’s question on whether a school should allow it if a student wants to take two CCAs –
30 | SPEECH | 1012 | Mr Yee Jenn Jong | More than two CCAs.
31 | SPEECH | 937 | Mr Heng Swee Keat | Well, I think in my comments on holistic and student-centric education, my key point is that everyone is different and, therefore, we should not be overly presc
32 | SPEECH | 937 | Mr Heng Swee Keat | Now, on the Member’s question about whether students should take more or fewer subjects: it is exactly the same philosophy. There are students who have done ver
33 | SPEECH | 983 | Mr Speaker | Dr Ng Eng Hen, do you have a clarification?
34 | SPEECH | 979 | Dr Ng Eng Hen | Mr Speaker, thank you for allowing me to make some clarifications on my previous reply. I think Dr Lim Wee Kiak had asked for Dr Patrick Tan’s service during his operationally-ready national service, in other words, after national service, full-time national service. I was looking for the paragraph, and I have found it. Dr Patrick Tan served as a Laboratory Officer in one of the SAF’s combat support hospitals. This is a standard designation in the combat support hospital. The role of the Laboratory Officer is to assist with blood and plasma storage and supply and to conduct clinical analysis of blood samples. I presume he was deployed there because of his qualifications.
35 | SPEECH | 979 | Dr Ng Eng Hen | My last clarification was in terms of what Mr Yaw brought up in terms of the "white horse" issue. I said that Mr Cedric Foo had answered the question previously and to refer to the reply. If Members checked the record of the reply, I think he made it clear the "white horse" policy was initiated to ensure that there was no preferential treatment given to anyone in regard to NS.
"""
_REPORT_12949_TITLE = (
    "Findings from Trial of Using Speed-tracking Devices for Heavy Vehicles"
)
_REPORT_12949_ROWS = """
1 | SPEECH | 1093 | Mr Louis Ng Kok Kwang | asked the Minister for Home Affairs (a) what are the findings from the trial of using speed-tracking devices for heavy vehicles in 2018; and (b) whether there a
2 | SPEECH | 1019 | The Senior Parliamentary Secretary to the Minister for Home Affairs (Mr Amrin Amin) (for the Minister for Home Affairs) | Today, the Traffic Police (TP) already require the use of speed limiters for heavy vehicles. One limitation, however, is that the speed limiters can be tampered
3 | SPEECH | 1019 | The Senior Parliamentary Secretary to the Minister for Home Affairs (Mr Amrin Amin) (for the Minister for Home Affairs) | Between December 2017 and August 2018, TP conducted a trial on speed-tracking devices, to assess if they might be more effective than speed limiters in discoura
4 | SPEECH | 1019 | The Senior Parliamentary Secretary to the Minister for Home Affairs (Mr Amrin Amin) (for the Minister for Home Affairs) | In addition, the cost to install the speed tracking devices is not low. TP has decided not to make the speed tracking devices mandatory. TP will continue to req
5 | SPEECH | 1019 | The Senior Parliamentary Secretary to the Minister for Home Affairs (Mr Amrin Amin) (for the Minister for Home Affairs) | TP will continue to monitor the development of other technologies that can help to discourage speeding. TP will also continue to adopt a multi-pronged strategy
6 | SPEECH | 1111 | Mr Speaker | Mr Louis Ng.
7 | SPEECH | 1093 | Mr Louis Ng Kok Kwang (Nee Soon) | I thank the Senior Parliamentary Secretary for the reply. My main concern really is that when there is an accident involving a heavy vehicle, the chance of fata
8 | SPEECH | 1093 | Mr Louis Ng Kok Kwang (Nee Soon) | My second question is whether MHA will consider installing the speed counters that we have in our military vehicles. We seldom see the military vehicles speedin
9 | SPEECH | 1019 | Mr Amrin Amin | I thank the Member for the suggestion. We will study whether we need to increase the penalties for tampering. But currently, the penalties are quite significant
10 | SPEECH | 1019 | Mr Amrin Amin | That said, we are not just stopping there. We are also looking to enhance the punishment, in particular. MHA recently announced increases in composition sums fo
11 | SPEECH | 1019 | Mr Amrin Amin | Also, TP engages heavy vehicle drivers regularly through education, safety dialogues and various other sessions.
12 | SPEECH | 1019 | Mr Amrin Amin | On the use of the speed tracking devices, that is part of the trial. In fact, what we have tested in the trial were enhanced features where the business owners
13 | SPEECH | 1019 | Mr Amrin Amin | On a good note, the accidents involving heavy vehicles have, in fact, decreased. Let me share with Member the figures that we have. Between 2014 and 2018, the n
14 | SPEECH | 1111 | Mr Speaker | Senior Parliamentary Secretary Low Yen Ling.
15 | SPEECH | 1082 | The Senior Parliamentary Secretary to the Minister for Education (Ms Low Yen Ling) | Thank you, Mr Speaker, Sir. Please allow me to respond to the earlier clarification by Dr Intan Mokhtar. The child psychology clinic that she cited was reported by The New Paper in a 2010 article, and this child psychology clinic was just one of the initiatives that Temasek Polytechnic was considering. This initiative was never implemented and Mr Brochez was not involved in this initiative.
16 | SPEECH | 1111 | Mr Speaker | Order. End of Question Time. Introduction of Government Bills.
"""


def test_report_20882_later_holders_clarification_of_a_previous_reply_is_not_an_answer() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_20882_TITLE,
        _REPORT_20882_ROWS,
        speaker_id_to_office={
            979: Office(
                "Minister for Defence and Leader of the House",
                OfficeSource.ATTENDANCE_LIST,
            )
        },
    )

    assert _get_person_rows(labelled_report, 979) == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            34,
            "Dr Ng Eng Hen",
            979,
        )
    ]


def test_report_12949_later_holders_response_to_an_earlier_clarification_is_not_an_answer() -> (
    None
):
    labelled_report = _label_report(_REPORT_12949_TITLE, _REPORT_12949_ROWS)

    assert _get_person_rows(labelled_report, 1082) == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            15,
            "The Senior Parliamentary Secretary to the Minister for Education (Ms Low Yen Ling)",
            1082,
        )
    ]


_REPORT_33485_TITLE = "PUBLIC ASSISTANCE ALLOWANCE"
_REPORT_33485_ROWS = """
1 | SPEECH | 298 | Mr Hwang Soo Jin | asked the Acting Minister for Social Affairs (a) how many people have had their public assistance allowance withdrawn in 1980; and (b) whether his Ministry ensures that every recipient of such allowance will be able to o
2 | SPEECH | 273 | The Acting Minister for Social Affairs (Dr Ahmad Mattar) | Mr Speaker, Sir, a total of 1,984 Public Assistance recipients had their allowances withdrawn last year, 1,586 or 80% of the total were supported by children or close relatives. Another 239 or 12% lost their allowances b
3 | SPEECH | 273 | The Acting Minister for Social Affairs (Dr Ahmad Mattar) | On the second part of the hon. Member's question, my Ministry does ensure that Public Assistance allowance is not withdrawn unless the recipient has adequate alternative means of support. In particular, a recipient will
4 | SPEECH | 338 | Mr Teo Chong Tee (Changi) | Mr Speaker, Sir, despite the Hon. Minister's assurance that the Public Assistance allowance is not withdrawn unless the recipient has adequate alternative means of support, I still receive a large number of appeals from constituents who complain about the stoppage of public assistance allowance. I am sure many of my colleagues in this House face the same problems with their constituents.
5 | SPEECH |  | Some hon. Members | Yes.
6 | SPEECH | 338 | Mr Teo Chong Tee | For example, in my Constituency there were about 210 public assistance recipients in 1979, and in 1980 the number was drastically reduced to about 90. Maybe the Director of Social Welfare is too strict in carrying out this exercise. May I ask what steps has the Hon. Minister taken to ensure that fair judgment is given to each and every case?
7 | SPEECH | 273 | Dr Ahmad Mattar | Mr Speaker, Sir, as you know, I have on many occasions in this House enunciated the principles which govern the administration of the Public Assistance Scheme. The application of these principles on individual cases call
8 | SPEECH | 273 | Dr Ahmad Mattar | Sir, with a view to ensuring some measure of uniformity of standards in the administration of Public Assistance Scheme, I have recently set up a Committee called the Public Assistance Review Committee, or PARC. I chair t
9 | SPEECH | 295 | Mr Ho See Beng | May I ask the Acting Minister for Social Affairs how much money has he saved from stopping this allowance to the 1,600-odd recipients?
10 | SPEECH | 273 | Dr Ahmad Mattar | Mr Speaker, Sir, I cannot give offhand the amount that has been "saved", as the Member put it. Perhaps if he wants, he can put in another question for Oral Answer. But since he is a Member of the PARC, he will know soon.
11 | SPEECH | 295 | Mr Ho See Beng | Does the Minister also know how much the good name of the Socialist Government like the PAP Government has suffered because of this withdrawal?
12 | SPEECH | 273 | Dr Ahmad Mattar | That is why the PARC is set up.
13 | SPEECH | 326 | Mr Seah Mui Kok (Bukit Ho Swee) | Sir, I am glad that the Acting Minister for Social Affairs has given us the assurance that there is a Public Assistance Review Committee to review the public assistance allowance that is given to the poor people. But I w
14 | SPEECH | 326 | Mr Seah Mui Kok (Bukit Ho Swee) | Therefore, Sir, I want the assurance of this Review Committee that in cases where the son or daughter who gives such kind of assurance in writing in order to save face but does not actually give the money to the parents,
15 | SPEECH | 273 | Dr Ahmad Mattar | Mr Speaker, Sir, first of all, I would like to request the hon. Member for Bukit Ho Swee to submit to me this particular case or similar cases he has in mind. What I would like to say is that I would assure the House tha
16 | SPEECH | 326 | Mr Seah Mui Kok | Mr Speaker, Sir, "submit another Question" - this is the style of the Minister. But no. What I want to know is this, can the Minister give us an assurance that the son or daughter who has given a written assurance of giv
17 | SPEECH | 273 | Dr Ahmad Mattar | Sir, first of all, I would request the hon. Member for Bukit Ho Swee to give me the particular case he is talking about. If the sons or daughters, as he has said, had pledged or made written statements to say that they a
18 | SPEECH | 298 | Mr Hwang Soo Jin (Jalan Kayu) | Mr Speaker, Sir, two supplementary questions. First of all, to have 1,984 cases withdrawn within a course of one year. Does it not suggest that, in the first instance, there must be something wrong with the approving sys
19 | SPEECH | 273 | Dr Ahmad Mattar | As to the second question, Sir, it is my policy, which I have directed to the officials of the Ministry, to keep Members of Parliament informed of the outcome of their appeals referred to the Ministry.
20 | SPEECH |  | Some hon. Members | No!
21 | SPEECH | 273 | Dr Ahmad Mattar | In particular, those Members of Parliament who refer their cases to me personally, I make sure that I reply to them personally too.
22 | SPEECH | 273 | Dr Ahmad Mattar | On the first question about the breakdown which the hon. Member for Jalan Kayu has asked for, the reasons for withdrawing the allowances are as follows.
23 | SPEECH | 298 | Mr Hwang Soo Jin | On a point of clarification, Sir. I do not think I have asked for a breakdown. All that I said was that to have a situation where 1,984 cases are withdrawn within a course of one year, there must be something basically w
24 | SPEECH | 273 | Dr Ahmad Mattar | Sir, the Member's request will be looked into.
"""


def test_report_33485_office_guessed_from_the_parliament_does_not_make_an_answerer() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_33485_TITLE,
        _REPORT_33485_ROWS,
        speaker_id_to_office={
            _TEO_CHONG_TEE_SPEAKER_ID: Office(
                "The Parliamentary Secretary to the Minister for Social Affairs",
                OfficeSource.PARLIAMENT_GUESS,
            )
        },
    )

    assert _get_person_rows(labelled_report, _TEO_CHONG_TEE_SPEAKER_ID) == [
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            4,
            "Mr Teo Chong Tee (Changi)",
            338,
        )
    ]
    assert _summarise_office_marks(
        [
            report_participant
            for report_participant in labelled_report.participants
            if report_participant.speaker_id == _TEO_CHONG_TEE_SPEAKER_ID
        ]
    ) == [
        (
            ParticipantRole.SUPPLEMENTARY,
            338,
            None,
            "The Parliamentary Secretary to the Minister for Social Affairs",
            OfficeClass.PARLIAMENTARY_SECRETARY,
            OfficeSource.PARLIAMENT_GUESS,
        )
    ]


_REPORT_42915_TITLE = "CONSTRUCTION INDUSTRY"
_REPORT_42915_ROWS = """
1 | SPEECH | 626 | Mr Goh Chong Chia | asked the Minister for National Development whether he will consider releasing more public sector work to the private sector instead of giving the work directly to Government corporatised companies as the construction industry has yet to recover from
2 | SPEECH | 626 | Mr Goh Chong Chia (Nominated Member) | Mr Speaker, Sir, in asking Question No. 6, I wish to declare that I am an architect in private practice.
3 | SPEECH |  | The Minister of State for National Development (Dr John Chen Seow Phun (for the Minister for National Development)) | Mr Speaker, Sir, the Public Works Department (PWD) was corporatised in 1999 as part of the Government's efforts to progressively devolve its non-policy and non-regulatory functions to the private sector. This would benefit the private sector in the l
4 | SPEECH |  | The Minister of State for National Development (Dr John Chen Seow Phun (for the Minister for National Development)) | To effect the corporatisation, the Government granted the corporatised PWD a moratorium period of five years starting from 1st April 1999. During this period, PWDCorp Pte Ltd is to continue with architectural and engineering consultancy, project mana
5 | SPEECH |  | The Minister of State for National Development (Dr John Chen Seow Phun (for the Minister for National Development)) | The private sector has in fact benefited as a result of the PWD corporatisation. Before its corporatisation, PWD was handling all Ministry projects. Since corporatisation, the Government has directly awarded more than $450 million worth of projects e
6 | SPEECH | 682 | Mr Simon S C Tay (Nominated Member) | Sir, I believe the Minister of State mentioned $450 million worth of contracts. Could I know how much this is as a percentage of the works given out by the Government?
7 | SPEECH | 612 | Dr John Chen Seow Phun | Sir, I do not have the figures with me, but let me just do a mental calculation. For $450 million, if you exclude the big projects, eg, reclamation and so on, I would say maybe in the region of 10%-20%. It is just a guess.
8 | SPEECH | 682 | Mr Simon Tay | Sir, I appreciate the Minister of State doing his back-of-envelope work. 10%-20%, if it excludes the very large projects like reclamation, seems a little low, if I may say. Is there any inclination to push it up higher? Is the private sector up to th
9 | SPEECH | 612 | Dr John Chen Seow Phun | Sir, may I remind the hon. Member that PWD was formerly part of the Government and all the jobs were given to PWD. This moratorium is basically to ensure a smooth transition. PWD is now in the private sector and, therefore, it has to compete with the
10 | SPEECH | 685 | Mr Thomas Thomas (Nominated Member) | Sir, since PWD is now privatised and in the private sector, can the Minister of State tell us how much private-sector work is PWD doing?
11 | SPEECH | 612 | Dr John Chen Seow Phun | Sir, this is a related question. If I know the exact figure, I would have been able to give the percentage to the hon. Member. However, now that he has jogged my memory, PWD is doing a lot of Government work, eg, schools, even the Terminal 3 design a
12 | SPEECH | 626 | Mr Goh Chong Chia | Mr Speaker, Sir, in view of the prolonged recession in the construction industry, would the Government consider reviewing the moratorium?
13 | SPEECH | 612 | Dr John Chen Seow Phun | Sir, we have forwarded the feedback to the Ministry of Finance and I believe they are currently reviewing it.
"""
_REPORT_25916_TITLE = "REVERSE MORTGAGES FOR HDB FLATS"
_REPORT_25916_ROWS = """
1 | SPEECH | 684 | Dr Teo Ho Pin | asked the Minister for National Development whether the Housing and Development Board will allow its lessees especially senior citizens to take up reverse mortgages for their flats so that they can have more disposable income.
2 | SPEECH |  | The Minister of State for National Development (Dr John Chen Seow Phun (for the Minister for National Development)) | Mr Speaker, Sir, the Ministry of National Development and the Housing and Development Board have explored reverse mortgage as a possible way to provide elderly HDB lessees with an additional source of income for their retirement needs.
3 | SPEECH |  | The Minister of State for National Development (Dr John Chen Seow Phun (for the Minister for National Development)) | The current reverse mortgage proposals allow a property owner to receive monthly payments over a fixed term of about 10 years. At the end of a reverse mortgage term, however, the property owner has to relinquish ownership of his house unless he is ab
4 | SPEECH |  | The Minister of State for National Development (Dr John Chen Seow Phun (for the Minister for National Development)) | After studying the conditions and implications of current reverse mortgage proposals carefully, we feel that the benefits are outweighed by the inherent limitations. The monthly payments are relatively meagre because of high financing costs. More imp
5 | SPEECH | 682 | Mr Simon Tay | May I ask the Minister of State whether this is a form of paternalism and it goes against the idea that citizens should take more responsibility for managing their own assets?
6 | SPEECH | 612 | Dr John Chen Seow Phun | Sir, I think it is not prudent. There is a risk involved and if the elderly stands to lose his home, then I do not think it is prudent for Government to start this scheme because basically we want to encourage home ownership.
7 | SPEECH | 682 | Mr Simon Tay | Sir, even if we open up the possibility, it will still be an option for the elderly. Is it not possible, therefore, that an elderly couple could be sitting on a fully paid-up flat but they have no money in their pockets, and would that not be a hards
8 | SPEECH | 612 | Dr John Chen Seow Phun | Mr Speaker, Sir, we have other schemes to help them. In fact, we have a number of them. For instance, we have made it easier for elderly lessees of three-room flats to sublet their whole flat. Is it not better? And if they do not wish to move, and th
9 | SPEECH | 686 | Assoc. Prof. Toh See Kiat | Sir, I would like to ask the Minister of State whether he is aware that sometimes the HDB officials will send letters to elderly lessees, who are alone, as an almost automatic reaction to tell them to give up their flat and sell it away, and this rea
10 | SPEECH | 612 | Dr John Chen Seow Phun | Sir, I am not aware of this. If the Member has the details, please pass it to me.
"""
_REPORT_31140_TITLE = "BRAIN DRAIN PROBLEM"
_REPORT_31140_ROWS = """
1 | SPEECH | 417 | Dr Wong Kwei Cheong | asked the Minister for Home Affairs (a) how serious is the brain drain problem for Singapore in terms of the number of Singaporeans who have emigrated and renounced their Singapore citizenship over the last ten years; and (b) under what conditions th
2 | SPEECH |  | The Minister of State for Home Affairs (Dr Lee Boon Yang (for the Minister for Home Affairs)) | Sir, I am answering on behalf of my Minster.
3 | SPEECH |  | The Minister of State for Home Affairs (Dr Lee Boon Yang (for the Minister for Home Affairs)) | Sir, statistics from the Registry of Citizens show that from 1977 to October 1987, 8,144 persons had renounced their Singapore citizenship. In the same period, 2,772 persons had their Singapore citizenship terminated on the ground that they had taken
4 | SPEECH |  | The Minister of State for Home Affairs (Dr Lee Boon Yang (for the Minister for Home Affairs)) | These statistics tell one part of the story. During the same 10-year period, 88,132 persons acquired Singapore citizenship. Another 67,400 persons became permanent residents. Of the permanent residents, many will acquire citizenship eventually if the
5 | SPEECH |  | The Minister of State for Home Affairs (Dr Lee Boon Yang (for the Minister for Home Affairs)) | Sir, the Prime Minister and the First Deputy Prime Minister have recently dis- cussed in detail the implications of Singaporeans emigrating in significant numbers. Every Singaporean, especially a skilled and talented person, who decides to leave perm
6 | SPEECH |  | The Minister of State for Home Affairs (Dr Lee Boon Yang (for the Minister for Home Affairs)) | Singaporeans are free to travel. We cannot prevent people from leaving. Therefore, we must make life in Singapore more satisfying so that fewer people will want to emigrate. While we cannot duplicate the ski-slopes and natural sceneries of Vancouver
7 | SPEECH |  | The Minister of State for Home Affairs (Dr Lee Boon Yang (for the Minister for Home Affairs)) | We do not place any impediment in the way ex-Singaporeans who wish to work in Singapore so long as they have recognized qualifications or skills and can contribute positively to our nation. When they apply for permits to work in Singapore, the Immigr
"""


def test_report_42915_label_with_the_for_bracket_nested_in_the_name_is_one_answerer_with_the_person() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_42915_TITLE,
        _REPORT_42915_ROWS,
        inline_label_to_speaker_id={"Dr John Chen Seow Phun": _JOHN_CHEN_SPEAKER_ID},
    )

    assert _get_person_rows(labelled_report, _JOHN_CHEN_SPEAKER_ID) == [
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            3,
            "The Minister of State for National Development (Dr John Chen Seow Phun (for the Minister for National Development))",
            _JOHN_CHEN_SPEAKER_ID,
        )
    ]
    assert _summarise_office_marks(
        [
            report_participant
            for report_participant in labelled_report.participants
            if report_participant.role == ParticipantRole.ANSWERER
        ]
    ) == [
        (
            ParticipantRole.ANSWERER,
            _JOHN_CHEN_SPEAKER_ID,
            "for the Minister for National Development",
            "The Minister of State for National Development",
            OfficeClass.MINISTER_OF_STATE,
            OfficeSource.LABEL_IN_REPORT,
        )
    ]
    assert [
        report_participant.speaker_id
        for report_participant in labelled_report.participants
        if report_participant.role == ParticipantRole.ANSWERER
    ] == [_JOHN_CHEN_SPEAKER_ID]


def test_report_25916_label_with_the_for_bracket_nested_in_the_name_is_one_answerer_with_the_person() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_25916_TITLE,
        _REPORT_25916_ROWS,
        inline_label_to_speaker_id={"Dr John Chen Seow Phun": _JOHN_CHEN_SPEAKER_ID},
    )

    assert _get_person_rows(labelled_report, _JOHN_CHEN_SPEAKER_ID) == [
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            2,
            "The Minister of State for National Development (Dr John Chen Seow Phun (for the Minister for National Development))",
            _JOHN_CHEN_SPEAKER_ID,
        )
    ]


def test_report_31140_label_with_the_for_bracket_nested_in_the_name_stores_it_with_no_person_to_merge() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_31140_TITLE,
        _REPORT_31140_ROWS,
        inline_label_to_speaker_id={"Dr Lee Boon Yang": 381},
    )

    assert _summarise_participants(labelled_report.participants)[1] == (
        ParticipantRole.ANSWERER,
        ParticipantRoleSource.OFFICE_LABEL,
        2,
        "The Minister of State for Home Affairs (Dr Lee Boon Yang (for the Minister for Home Affairs))",
        None,
    )
    assert _summarise_office_marks(labelled_report.participants) == [
        (
            ParticipantRole.ANSWERER,
            None,
            "for the Minister for Home Affairs",
            None,
            None,
            None,
        )
    ]


_REPORT_30999_TITLE = "PRIMARY AND SECONDARY SCHOOLS"
_REPORT_30999_ROWS = """
1 | UNCLASSIFIED |  |  | The following Question stood in the name of Mr Chiam See Tong -
2 | DOCUMENT_TEXT |  |  | 4. To ask the Minister for Education what progress has been made in reducing the number of students in primary and secondary school classes.
3 | SPEECH | 424 | Mr Speaker | Mr Chiam.
4 | SPEECH | 411 | Dr S. Vasoo (Bo Wen) | Question 4, Sir.
5 | SPEECH | 403 | Mr Tan Soo Khoon (Alexandra) | Mr Chiam is not here, Sir. Question 4.
6 | SPEECH | 407 | The Minister of State for Education (Dr Tay Eng Soon) (for the Minister for Education) | Mr Speaker, Sir, I thank the Backbenchers for coming out so promptly to raise the Question on behalf of the Member for the Opposition.
7 | SPEECH | 407 | The Minister of State for Education (Dr Tay Eng Soon) (for the Minister for Education) | Sir, I am answering on behalf of my Minister. The reduction of class size in primary and secondary schools is a gradual process. It is dependent on two major factors - teachers and school buildings.
8 | SPEECH | 407 | The Minister of State for Education (Dr Tay Eng Soon) (for the Minister for Education) | Class size can be reduced only when there is a corresponding increase in the number of teachers. Efforts have been and are being made to attract more people to join the teaching profession. These efforts are currently being stepped up.
9 | SPEECH | 407 | The Minister of State for Education (Dr Tay Eng Soon) (for the Minister for Education) | Smaller class size means more classrooms and school buildings. With secondary schools going single session, the demand for more school buildings will become even greater. It takes time to build schools.
10 | SPEECH | 407 | The Minister of State for Education (Dr Tay Eng Soon) (for the Minister for Education) | The reduction of class size is a desirable objective which is being pursued in our quest for excellence in education. However, it cannot be brought about overnight.
"""


def test_report_30999_second_member_who_reads_out_the_same_question_is_also_a_reader() -> (
    None
):
    labelled_report = _label_report(_REPORT_30999_TITLE, _REPORT_30999_ROWS)

    assert [
        participant
        for participant in _summarise_participants(labelled_report.participants)
        if participant[0] == ParticipantRole.READER
    ] == [
        (
            ParticipantRole.READER,
            ParticipantRoleSource.ASKER_RULES,
            4,
            "Dr S. Vasoo (Bo Wen)",
            _VASOO_SPEAKER_ID,
        ),
        (
            ParticipantRole.READER,
            ParticipantRoleSource.QUESTION_NUMBER_CALL,
            5,
            "Mr Tan Soo Khoon (Alexandra)",
            403,
        ),
    ]
    assert ParticipantRole.UNLABELLED not in {
        participant.role for participant in labelled_report.participants
    }


_REPORT_37380_TITLE = "RISE IN COST OF LIVING"
_REPORT_37380_ROWS = """
1 | UNCLASSIFIED |  |  | The following Question stood in the name of Inche Mohd. Ariff Bin Suradi -
2 | DOCUMENT_TEXT |  |  | 6. To ask the Minister for Finance whether he is aware that the cost of living in the Republic has gone up rapidly and if he is taking any steps in the matter.
3 | SPEECH | 55 | Mr Tang See Chim | Inche Mohd. Ariff Bin Suradi.
4 | SPEECH | 47 | Inche Rahamat Bin Kenap (Geylang Serai) | Question No. 6.
5 | SPEECH | 20 | Dr Goh Keng Swee | Sir, for some months there has been public concern over increases in the prices of certain commodities, especially foodstuffs and household articles. The reasons for these price increases are often confused in the public mind. As a result, there have
6 | SPEECH | 20 | Dr Goh Keng Swee | What can Government do about the price of rice? First, we must find out why the price has gone up. Is it due to profiteering by our rice merchants, or is it because the world price of rice has increased? If price increases are the result of profiteer
7 | SPEECH | 20 | Dr Goh Keng Swee | So long as people want to eat rice, they must pay for the extra cost. But they can economise by eating less rice and more wheat products, such as bread and noodles, as our Deputy Prime Minister has been advocating. Wheat flour, of course, is half the
8 | SPEECH | 20 | Dr Goh Keng Swee | There has also been a substantial increase in the price of canned meat imported from China. Chinese exporters have increased their prices, and there is statistical evidence that this has happened. Here again the reasons lie outside our country and be
9 | SPEECH | 20 | Dr Goh Keng Swee | As regards day-to-day food supplies, certain items have gone up in price, such as cabbages and potatoes, while others have gone down in price, such as red chillies, onions, spinach, chai sim and 1ong beans. These are normal fluctuations in the market
10 | SPEECH | 20 | Dr Goh Keng Swee | Some months ago there was an attempt made to speculate in matches and sugar. When these commodities were produced in Singapore, import duties were imposed on foreign products so that the local manufacturer could capture the domestic market. Some peop
11 | SPEECH | 20 | Dr Goh Keng Swee | This brings me to the subject of Government's policy on industrialisation and its effect on the prices of goods. We must assure the local manufacturer a substantial portion of the domestic market for the products he is manufacturing. To do this, impo
12 | SPEECH | 20 | Dr Goh Keng Swee | In two or three instances there are grounds for suspecting local manufacturers of either having inefficient high cost management or making excessive profits. The cure here, in the first instance, is to improve management efficiency. In the second cas
13 | SPEECH | 22 | Mr P. Govindaswamy (Anson) | As the Hon. Minister for Finance has accepted the fact that people earning below $200 will incur an additional expenditure of $14, will the Minister consider increasing the salaries of people drawing low pay?
14 | SPEECH | 20 | Dr Goh Keng Swee | The answer is "No".
15 | SPEECH | 58 | Mr Teong Eng Siong (Sembawang) | Will the Minister consider requesting all shops selling foodstuffs to exhibit price tags on their goods (especially rice) for public information?
16 | SPEECH | 16 | Mr Speaker | Mr Teong, the subject matter of your supplementary is actually a substantive question. It is down today for written answer. So your supplementary, in fact, anticipates a matter that is before the House.
17 | SPEECH | 58 | Mr Teong Eng Siong | I would like to ask the Minister whether he would consider instructing all rice sellers to exhibit price tags to help the buyers. Some of the shops have already done so.
18 | SPEECH | 20 | Dr Goh Keng Swee | I do not believe that exhibiting price tags could reduce the price of rice. But if the hon. Member believes that it will, and has confidence in its efficacy, then we can give it a try.
19 | SPEECH | 58 | Mr Teong Eng Siong | Sir, what I mean is that if there are price tags, the purchasers will know the actual condition of the market, because now and then, whenever there is any incident, the seller -
20 | SPEECH | 16 | Mr Speaker | Mr Teong, supplementaries are not explanations.
21 | SPEECH | 55 | Mr Tang See Chim (Choa Chu Kang) | Mr Speaker, Sir, would the Minister for Finance consider setting up a committee whose sanction is necessary if any local manufacturer wishes to increase the price of his products?
22 | SPEECH | 20 | Dr Goh Keng Swee | There are committees in existence to consider applications from manufacturers who wish to increase the prices of their goods.
23 | SPEECH | 55 | Mr Tang See Chim | Does it mean that the present position is that no local manufacturers can increase the prices of their products unless the increase is sanctioned by the committee that is in existence?
24 | SPEECH | 20 | Dr Goh Keng Swee | They are under no legal compulsion to keep their prices at any given level. But there is a gentleman's agreement between the Ministry and the manufacturers that price increases should be discussed with and agreed to between themselves. For this purpo
25 | SPEECH | 55 | Mr Tang See Chim | What sanction would there be then should a local manufacturer breach this gentleman's agreement?
26 | SPEECH | 20 | Dr Goh Keng Swee | The sanction I have mentioned, Mr Speaker, Sir, is the abolition of tariff protection.
"""
_REPORT_26045_TITLE = "'BABY BONUS' SCHEME"
_REPORT_26045_ROWS = """
1 | SPEECH | 605 | Mr Ang Mong Seng | asked the Prime Minister whether he will consider granting the 'Baby Bonus' to include the first child, and whether the effective date for this scheme will be the date of announcement instead of 1st April 2001.
2 | SPEECH | 650 | The Minister without Portfolio (Mr Lim Boon Heng) (for the Prime Minister) | The Total Fertility Rate or TFR was 1.48 in 1999. In other words, on average, each Singaporean woman was having at least one child. Therefore, it is not necessary to provide incentives for the birth of the first child. The "baby bonus" and other pro-
3 | SPEECH | 650 | The Minister without Portfolio (Mr Lim Boon Heng) (for the Prime Minister) | The effective date has been decided after taking into consideration the time for families to respond to the call for bigger families. There is no one date, which will satisfy all parties. Even if it were effective from the date of announcement, there
4 | SPEECH | 661 | Dr Lily Neo (Kreta Ayer-Tanglin) | Will the Minister clarify whether the "baby bonus" would be given to those who conceived after the announcement but deliver before 1st April 2001 due to unforeseen premature births?
5 | SPEECH | 650 | Mr Lim Boon Heng | Mr Speaker, Sir, I think it is very difficult to be precise as to the date of conception. Some allowance has already been provided in the announcement that it will be effective from 1st April 2001.
6 | SPEECH | 661 | Dr Lily Neo | May I ask the Minister whether it is unfair to these couples who have responded to the call for having more children after the Prime Minister's announcement and yet be deprived of the "baby bonus" because of nature and not through the fault of their
7 | SPEECH | 650 | Mr Lim Boon Heng | Sir, it is not a matter of fairness. We have to look at this "baby bonus" in its proper perspective. It is an encouragement to families to have more children. We cannot count every dollar and cent as to who would benefit and who would not. As in draw
8 | SPEECH | 687 | Dr S. Vasoo (Tanjong Pagar) | Can I ask the Minister why are they so clinical? Why can we not be more generous, since people are responding to the call?
9 | SPEECH | 650 | Mr Lim Boon Heng | We are not trying to be clinical. We are trying to set a date for implementation. As I said in my earlier answer, even if we set the effective date at the point of time when the Prime Minister made the announcement, some people will still miss it.
10 | SPEECH | 658 | Mr Low Thia Khiang | Does the Minister not think that parents who do not need encouragement but already have more children in contributing to the population growth should also be given some rewards?
11 | SPEECH | 650 | Mr Lim Boon Heng | Mr Speaker, Sir, we should look at this in its proper perspective. We have a falling fertility rate. What Government can do is to offer incentives as a signal to the people that we encourage families to have children. As I said, it is not a question
12 | SPEECH | 605 | Mr Ang Mong Seng (Bukit Gombak) | Sir, the "baby bonus" is geared towards encouraging the families to have more babies, but it should not be confined to monetary measures only. Concessions in childcare centres and priority in housing should be given as incentives for them to produce
13 | SPEECH | 650 | Mr Lim Boon Heng | Some of the measures to encourage couples to have children have been announced. I know that there are many other suggestions that people would have on how we can give further encouragement to couples to do so. The measures which Mr Ang mentioned will
14 | SPEECH | 661 | Dr Lily Neo | May I suggest another important incentive, ie, to encourage young married couples to start having children earlier in order to address the present trend of later marriages and postponement of having children?
15 | SPEECH | 650 | Mr Lim Boon Heng | If the Member has effective suggestions as to how to encourage people to marry younger and have children younger, please forward the suggestions.
16 | SPEECH | 687 | Dr Vasoo | Sir, even if our parliamentary colleagues are going to give suggestions on the issue of "baby bonus", the support from Government is just lukewarm.
17 | SPEECH | 679 | Mr Speaker | Dr Vasoo, are you asking a supplementary question or you are asking the next question?
18 | SPEECH | 687 | Dr Vasoo | Sir, I am trying to ask the Minister whether he would relook at the whole issue by encouraging younger people to have family formation and see whether we could be more generous by looking at other incentives which would be necessary to support popula
19 | SPEECH | 650 | Mr Lim Boon Heng | Mr Speaker, Sir, the cost of raising children varies from family to family but I hear that many people think it is not expensive. Whatever bonus or incentive that the Government gives to couples for raising their children cannot fully cover the total
20 | SPEECH | 650 | Mr Lim Boon Heng | The more difficult area to consider would be the social changes that have taken place in society, not only in ours but I think worldwide, and whether those changes can be reversed. It has to do with the values that people hold and when we talk about
21 | SPEECH | 679 | Mr Speaker | I think we have enough baby talk for one day. Can you ask the next question, Dr Vasoo?
22 | SPEECH | 687 | Dr Vasoo | Question No. 8.
"""
_REPORT_31695_TITLE = "PARKING OF MOTORCYCLES IN HDB VOID DECKS"
_REPORT_31695_ROWS = """
1 | SPEECH | 367 | Mr Goh Choon Kang | asked the Minister for National Development (a) how widespread is the problem of indiscriminate parking by motorcyclists at Housing and Development Board apartments' void decks; and (b) whether the HDB has any plan to deal with the problem.
2 | SPEECH | 359 | Mr Chiam See Tong (Potong Pasir) | Mr Speaker, Sir, I think there is a point of order. This question refers to indiscriminate parking of motorcycles in Housing and Development Board apartments' void decks. May I say that I have got no complaints in respect of the constituency of Poton
3 | SPEECH | 424 | Mr Speaker | It is a very unusual statement, Mr Chiam. You can ask a supplementary question if you want.
4 | SPEECH | 359 | Mr Chiam See Tong | Before the Minister gives his answer?
5 | SPEECH | 424 | Mr Speaker | You are pre-empting the Minister.
6 | SPEECH | 408 | The Minister for National Development (Mr Teh Cheang Wan) | Mr Speaker, Sir, in a recent sample survey of 189 apartment blocks in Serangoon Central, Tampines West and Hougang Central Estates, it was found that, on the average, two motorcycles were found parking in the void decks, per block, during the night.
7 | SPEECH | 408 | The Minister for National Development (Mr Teh Cheang Wan) | The HDB has served warning notices on motorcycles found parked in the void decks. Although this has resulted in getting some of the owners to park their motorcycles in authorized lots in the car parks, it has not eliminated the problem. Where the par
8 | SPEECH | 408 | The Minister for National Development (Mr Teh Cheang Wan) | To deal with the problem more effectively, the HDB is currently formulating rules to prohibit the parking of motorcycles in the void decks of apartment blocks. Offenders can then be fined under such rules.
9 | SPEECH | 375 | Mr J.B. Jeyaretnam (Anson) | Mr Speaker, Sir, supplementary question for the Minister, and that is: will he tell us whether adequate parking places for motorcyclists are provided in every housing estate, adjacent to the blocks where the residents are living? Is he aware that a n
10 | SPEECH | 408 | Mr Teh Cheang Wan | Mr Speaker, Sir, HDB has provided adequate motorcycle parking lots in the housing estates. Perhaps I can give the Member for Anson some figures. HDB manages a total of 103,118 motorcycle lots as at 30th June 1986, that is, up to middle of this year.
11 | SPEECH | 375 | Mr Jeyaretnam | Is the Minister aware that there have been complaints by residents who hold season parking tickets that when they come back at night, at 1 am or 2 am, after their work, they find all the parking lots taken up, maybe not by the season parking ticket h
12 | SPEECH | 408 | Mr Teh Cheang Wan | Those people who park their motorcycles without either season tickets or daily tickets are fined by HDB for taking up motorcycle lots which they are not supposed to. I do not think availability of parking lots is a problem. In most cases these motorc
13 | SPEECH | 359 | Mr Chiam See Tong | What steps has the HDB taken to publicize this problem or to educate the residents of housing estates not to park their motorcycles in void decks because of oil spills and other problems?
14 | SPEECH | 408 | Mr Teh Cheang Wan | Mr Speaker, Sir, I think periodically the HDB has publicized in the Home magazine the problem of parking motorcycles in the void decks, such as oil spills. And, as I have said earlier in answering the Member for Braddell Heights, HDB will be formulat
15 | SPEECH | 359 | Mr Chiam See Tong | Since the HDB knew of this problem, in what housing estates have they publicized and carried out a programme of education in regard to this problem?
16 | SPEECH | 408 | Mr Teh Cheang Wan | I said it is publicized in our HDB Home magazine, which means that since all HDB residents receive a copy of the Home magazine, so all HDB residents in every estate are told of this problem.
"""
_REPORT_31724_TITLE = "HUDC PHASE 3 FLATS"
_REPORT_31724_ROWS = """
1 | UNCLASSIFIED |  |  | The following Question stood in the name of Dr Koh Lam Son -
2 | DOCUMENT_TEXT |  |  | 2. To ask the Minister for National Development whether the Housing and Development Board will consider lifting the income ceiling and other qualifications for the purchase of HUDC phase 3 flats in view of the recent no-buy-back decision.
3 | SPEECH | 386 | Mr Leong Horn Kee (Thomson) | Question No. 2, Sir.
4 | SPEECH | 359 | Mr Chiam See Tong | Sir, I think this is important. May I ask a supplementary question?
5 | SPEECH | 424 | Mr Speaker | You can raise that after the question has been answered. Mr Teh.
6 | SPEECH | 408 | Mr Teh Cheang Wan | Mr Speaker, Sir, the present income ceiling for HUDC applicants of $6,000/- a month is based on the survey of household incomes in Singapore. 95% of families in Singapore qualify to purchase HUDC flats under the present income ceiling. As practically
7 | SPEECH | 408 | Mr Teh Cheang Wan | As HUDC housing provides long-term accommodation for middle-income families unable to afford private properties, it is necessary to impose other eligibility conditions such as requirements for citizenship, family nucleus and non-ownership of private
8 | SPEECH | 408 | Mr Teh Cheang Wan | The HDB has, therefore, no intention of lifting the income ceiling or the other eligibility conditions for the purchase of HUDC flats. This is also in line with the Government's policy not to compete with the private sector in the property market.
9 | SPEECH | 359 | Mr Chiam See Tong | Sir, a supplementary question as regards the previous Question which you have allowed me to ask.
10 | SPEECH | 424 | Mr Speaker | I am saying your supplementary question for the second Question.
11 | SPEECH | 359 | Mr Chiam See Tong | But we have not completed it.
12 | SPEECH | 424 | Mr Speaker | I am sorry to say it is completed. If you ask a supplementary question on the second Question, I will allow you. Do that please.
13 | SPEECH | 359 | Mr Chiam See Tong | I will ask a supplementary question. The Minister has conceded that HUDC policy is under the HDB rules. Is it not HDB's rule that the HDB purchases flats back from HDB house owners within five years? Is that not a rule?
14 | SPEECH | 408 | Mr Teh Cheang Wan | Mr Speaker, Sir, as I have explained very clearly and repeatedly just now, a lot of HDB and HUDC rules are similar but they are not identical.
15 | SPEECH | 359 | Mr Chiam See Tong | Sir, can the Minister please tell the House that the rule governing HUDC policy is, in fact, not completely governed by HDB rule. Is that what he is saying now? You are making so many exceptions.
16 | SPEECH | 408 | Mr Teh Cheang Wan | Mr Speaker, Sir, I think the Member for Potong Pasir is confused. Both the HUDC flat and HDB flat are governed by HDB rules.
17 | SPEECH | 359 | Mr Chiam See Tong | Correct.
18 | SPEECH | 408 | Mr Teh Cheang Wan | It is correct. But HDB has made various rules governing, for example, the 1-room flat which has separate rules.
19 | SPEECH | 359 | Mr Chiam See Tong | We are talking about the purchasing of flats back now.
20 | SPEECH | 424 | Mr Speaker | The Minister is answering the question.
21 | SPEECH | 408 | Mr Teh Cheang Wan | I am answering the question. I am just explaining that in all Housing Board flats, each flat type has its own rules. For example, the 1-room flat rules are different from the 2-room flat rules; the 2-room flat rules are different from other types of
22 | SPEECH | 359 | Mr Chiam See Tong | Answer the question.
23 | SPEECH | 408 | Mr Teh Cheang Wan | HDB flats, the 1-room, 2-room and 3-room flats, are offered for sale and they are also offered for rental. For the rental flats, the rules are different from the rules for sale of the flats, and I just ---
24 | SPEECH | 359 | Mr Chiam See Tong | Mr Speaker, Sir, this is wasting the House time. Please answer whether you have a rule to purchase back within five years.
25 | SPEECH | 424 | Mr Speaker | Mr Chiam, will you please sit down!
26 | SPEECH | 408 | Mr Teh Cheang Wan | Sir, there is no such rule to purchase HUDC flats back in five years.
27 | SPEECH | 359 | Mr Chiam See Tong | HDB.
28 | SPEECH | 408 | Mr Teh Cheang Wan | Yes, HDB. I have explained.
29 | SPEECH | 359 | Mr Chiam See Tong | All right. Now he concedes that there is an HDB rule which the HDB purchases HDB flats back in five years. Now we go back to your previous policy.
30 | SPEECH | 424 | Mr Speaker | Let us have your supplementary question, Mr Chiam.
31 | SPEECH | 359 | Mr Chiam See Tong | Is there not a clause in your lease, which you so much would like to refer to, the legality of it? Is there not a clause in your lease which says that if there is a requirement for the house owner, the HUDC owner, to resell it back, they have to rese
32 | SPEECH | 408 | Mr Teh Cheang Wan | Mr Speaker, Sir, I think this has already been answered and I do not wish to repeat.
33 | SPEECH | 359 | Mr Chiam See Tong | Therefore, if the HDB has got this ruling, that ruling should cover HUDC flats. We are talking of legality now. Why is the HDB not ---
34 | SPEECH | 424 | Mr Speaker | Are you asking a supplementary question or not?
35 | SPEECH | 359 | Mr Chiam See Tong | Yes, all right. Why is the HDB not buying back HUDC flats within five years under your rules and under the agreement of lease? Clause 12 for your information.
36 | SPEECH | 408 | Mr Teh Cheang Wan | There is no such agreement in the HUDC clause that says HDB has to buy back HUDC flats.
37 | SPEECH | 424 | Mr Speaker | Let us call this End of Question Time since the Member for Potong Pasir seems to be a bit confused.
"""


def test_report_37380_member_who_also_supplements_has_no_unlabelled_row() -> None:
    labelled_report = _label_report(
        _REPORT_37380_TITLE,
        _REPORT_37380_ROWS,
        speaker_id_to_office={
            20: Office("Minister for Finance", OfficeSource.HEADER_IN_REPORT)
        },
    )

    assert _get_person_rows(labelled_report, 55) == [
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            21,
            "Mr Tang See Chim (Choa Chu Kang)",
            55,
        )
    ]


def test_report_26045_member_who_calls_the_next_question_keeps_only_his_supplementary() -> (
    None
):
    labelled_report = _label_report(_REPORT_26045_TITLE, _REPORT_26045_ROWS)

    assert _get_person_rows(labelled_report, 687) == [
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            8,
            "Dr S. Vasoo (Tanjong Pagar)",
            687,
        )
    ]


def test_report_31695_member_whose_point_of_order_comes_first_keeps_only_his_supplementary() -> (
    None
):
    labelled_report = _label_report(_REPORT_31695_TITLE, _REPORT_31695_ROWS)

    assert _get_person_rows(labelled_report, 359) == [
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            13,
            "Mr Chiam See Tong",
            359,
        )
    ]


def test_report_31724_member_who_asks_before_the_answer_keeps_only_his_supplementary() -> (
    None
):
    labelled_report = _label_report(
        _REPORT_31724_TITLE,
        _REPORT_31724_ROWS,
        speaker_id_to_office={
            408: Office(
                "Minister for National Development", OfficeSource.HEADER_IN_REPORT
            )
        },
    )

    assert _get_person_rows(labelled_report, 359) == [
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            9,
            "Mr Chiam See Tong",
            359,
        )
    ]


_REPORT_9432_TITLE = "Take-up Rate by Malay/Muslims of Existing National Financial and Estate Planning Programmes"
_REPORT_9432_ROWS = """
1 | SPEECH | 1215 | Dr Shahira Abdullah | asked the Minister for Social and Family Development and Minister-in-charge of Muslim Affairs (a) what is the current take-up rate by Malay/Muslims of the natio
2 | SPEECH | 1189 | The Minister for Social and Family Development and Minister-in-charge of Muslim Affairs (Mr Masagos Zulkifli B M M) | Mr Speaker, MoneySENSE is our national financial education programme that seeks to raise Singaporeans' financial literacy. Under MoneySense, there are various i
78 | SPEECH | 1207 | Mr Pritam Singh | If I have not answered any of the Minister's questions, please ask me again. I will be happy to answer them. Ours is a philosophical point. We take the position
81 | SPEECH | 1168 | The Second Minister for National Development (Ms Indranee Rajah) | Thank you, Mr Speaker. I just wanted to ask a clarification of the Leader of the Opposition because I was listening to his response.
82 | SPEECH | 1168 | The Second Minister for National Development (Ms Indranee Rajah) | I think he had started out by saying that the EIP should be revisited. Then, he said, reviewed. He then mentioned that in the manifesto, they took a philosophical position. But I am sorry because I still do not know what WP's position is.
83 | SPEECH | 1168 | The Second Minister for National Development (Ms Indranee Rajah) | So, could the Leader of the Opposition clarify? Is he saying today that the EIP should be abolished? Is the answer to that, yes or no? That is all I want to know. Or is he saying that it need not be abolished, we can just look to see how we improve it? That is all I wanted to understand.
84 | SPEECH | 1207 | Mr Pritam Singh | Well, it is a very nice way to close off our discussion on this topic. But I will be happy to clarify the doubts of the Leader of the House. The philosophical p
85 | SPEECH | 1207 | Mr Pritam Singh | The Government is the government of the day, it wants to retain the EIP for reasons which I would say are not totally illegitimate. I think it is important that
86 | SPEECH | 1207 | Mr Pritam Singh | I think that is our duty as an opposition also. Half the reason why I am asking for all that data on a neighbourhood-by-neighbourhood basis, over time – annuall
87 | SPEECH | 1223 | Mr Speaker | Ms Indranee Rajah.
88 | SPEECH | 1168 | Ms Indranee Rajah | Mr Speaker, I thank the Leader of the Opposition for his erudite answer, which did not answer my question. So, I think we both agree. Both, indeed, the Workers' Party and we, agree we do want a race-neutral society. We want to raise a society where everybody can live happily together. It is a question of how do we get there. And one of the things that the People's Action Party Government has put in place is the EIP.
89 | SPEECH | 1168 | Ms Indranee Rajah | The Workers' Party, in its manifesto, has said, abolish it. Mr Pritam Singh comes to Parliament today and says revisit, review underlying philosophy and a few other things. I just want to know, today, is the Workers' Party saying we should remove the EIP? If you are saying that we should do that, say so. On the other hand, if you are saying, keep the EIP but let us improve it and ameliorate the impact on minorities, say so. Then, I think we know where we both stand and where we are in agreement.
90 | SPEECH | 1223 | Mr Speaker | Mr Pritam Singh.
91 | SPEECH | 1207 | Mr Pritam Singh | We still aim to remove it but, until we get there, we have to, as Minister said, even out the rough edges as much as possible and, at some point, I hope my gene
156 | SPEECH | 1207 | Mr Pritam Singh | I think I can agree with the eventual outcome that even the Minister shares, which is to reach that race-neutral, race-blind end. To that extent, yes. I think y
157 | SPEECH | 1228 | The Senior Minister and Coordinating Minister for National Security (Mr Teo Chee Hean) | Mr Speaker, Sir, I had not intended to speak or ask any questions on this very important subject, but I thought that since I have slightly more white hair than most people here who have been speaking, I thought I would share a perspective.
158 | SPEECH | 1228 | The Senior Minister and Coordinating Minister for National Security (Mr Teo Chee Hean) | I would like to ask the Leader of the Opposition whether he thinks we should allow ethnic enclaves to form and just to see what happens, by abolishing the EIP today; and then, reach a situation where we were 50 years ago, 60 years ago, at the point of Independence; and then, try and correct it when all the problems arise?
159 | SPEECH | 1228 | The Senior Minister and Coordinating Minister for National Security (Mr Teo Chee Hean) | Or whether we should take what he calls a pre-emptive but the measures that we are taking today, to avoid such a situation arising?
160 | SPEECH | 1228 | The Senior Minister and Coordinating Minister for National Security (Mr Teo Chee Hean) | So, are we more likely to arrive at a situation where Singaporeans learn to live with each other on a daily basis by making sure that we live in an integrated way on a daily basis in our estates? Or are we more likely to do so if we allow Singaporeans to live in segregated estates?
161 | SPEECH | 1228 | The Senior Minister and Coordinating Minister for National Security (Mr Teo Chee Hean) | And also, are we more likely to level everyone up if we are able to identify the issues that each of the communities in Singapore may face and therefore have more targeted programmes for them?
162 | SPEECH | 1228 | The Senior Minister and Coordinating Minister for National Security (Mr Teo Chee Hean) | Or to ignore the differences? The Leader of the Opposition says we should be race-blind or race-neutral and just treat everybody as though they are exactly the same.
163 | SPEECH | 1228 | The Senior Minister and Coordinating Minister for National Security (Mr Teo Chee Hean) | And then, are we likely to arrive at a good solution, where we reach this eventual outcome? Or are we less likely to do so?
164 | SPEECH | 1228 | The Senior Minister and Coordinating Minister for National Security (Mr Teo Chee Hean) | And Mr Speaker, Sir, I would like to ask the Leader of the Opposition whether he agrees with me, because he mentioned more Members of Opposition in the House would lead to better outcomes. I would like to ask the Leader of the Opposition whether he agrees with me that these are matters of great sensitivity and have to be handled with great sensitivity, rather than be exploited for political purposes?
165 | SPEECH | 1207 | Mr Pritam Singh | Mr Speaker, I will deal with the last comment first. Is the Senior Minister suggesting that the WP is using these episodes for political purposes? The answer, I
166 | SPEECH | 1207 | Mr Pritam Singh | In terms of the series of hypotheticals that the Senior Minister put out, I think moving from one extreme to another extreme is probably not the policy approach
167 | SPEECH | 1207 | Mr Pritam Singh | But I hope it does not undermine or take away the point that philosophically, where does the WP want Singapore to go? And I do not think the PAP is very far awa
168 | SPEECH | 1207 | Mr Pritam Singh | But I think, by and large, we accept that we have to move forward in a way where Singapore, as a country, as a society, is strengthened. That should make things
169 | SPEECH | 1228 | Mr Teo Chee Hean | Speaker, Sir, I think there is a lesson to be learnt here between philosophy and methods. The philosophy, we can agree on. We all want a multiracial Singapore. We want Singaporeans to live together in multi-racial communities, not in segregated communities. I think even the WP agrees on that; the Leader of the Opposition says so too.
170 | SPEECH | 1228 | Mr Teo Chee Hean | But how do we get there? Those are methods. Methods can be adapted and changed. But we have the same philosophy that we want a multi-racial society Singapore, integrated housing, well-integrated communities and schools. We are more likely to get there with the HDB policies that we have today, with EIP, rather than what the WP is proposing. In fact, their manifesto says abolish it now; although the Leader of the Opposition seems to have shifted away from that because he realises that that is untenable.
171 | SPEECH | 1228 | Mr Teo Chee Hean | Are we more likely to achieve an integrated Singapore by having integrated housing or to abolish the EIP as the WP would propose today and have segregated housing. And then, how do we learn how to live together again? That is the question I have, Sir.
172 | SPEECH | 1228 | Mr Teo Chee Hean | I am glad to hear the Leader of the Opposition say that we should all not exploit the issues of race and religion for political purposes. I applaud that.
173 | SPEECH | 1223 | Mr Speaker | Order. End of Question Time. Ministerial Statement. Minister for Finance.
"""


def test_report_9432_later_holder_who_asks_a_member_is_supplementary_not_answerer() -> (
    None
):
    labelled_report = _label_report(_REPORT_9432_TITLE, _REPORT_9432_ROWS)

    assert [
        participant
        for participant in _summarise_participants(labelled_report.participants)
        if participant[0] == ParticipantRole.ANSWERER
        or participant[0] == ParticipantRole.SUPPLEMENTARY
    ] == [
        (
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            2,
            "The Minister for Social and Family Development and Minister-in-charge of Muslim Affairs (Mr Masagos Zulkifli B M M)",
            1189,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            78,
            "Mr Pritam Singh",
            1207,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            81,
            "The Second Minister for National Development (Ms Indranee Rajah)",
            1168,
        ),
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            157,
            "The Senior Minister and Coordinating Minister for National Security (Mr Teo Chee Hean)",
            1228,
        ),
    ]


_REPORT_22632_TITLE = (
    "AFFORDABILITY OF PUBLIC HOUSING AND DESIGN, BUILD AND SELL SCHEME"
)
_REPORT_22632_ROWS = """
1 | UNCLASSIFIED |  |  | The following questions stood on the Order Paper -
2 | SPEECH | 865 | Dr Muhammad Faishal Ibrahim | To ask the Minister for National Development with the rising prices of new and resale HDB flats, what plans does the Government have to ensure that home ownership continu
3 | SPEECH | 872 | Dr Ong Seh Hong | To ask the Minister for National Development whether he can provide the rationale for the shift from providing affordable housing to the Design, Build and Sell Scheme fla
4 | SPEECH | 816 | Ms Eunice Elizabeth Olsen | To ask the Minister for National Development whether his Ministry will consider raising the income ceiling of $8,000 for the purchase of HDB flats under the Design, Build
5 | SPEECH | 850 | Mr Liang Eng Hwa (Holland-Bukit Timah) | Question No. 8, Sir.
6 | SPEECH | 862 | The Minister for National Development (Mr Mah Bow Tan) | Mr Speaker, Sir, may I have your permission to take Question Nos. 8, 9 and 10 together?
7 | SPEECH | 805 | Mr Speaker | Yes, please.
8 | SPEECH | 862 | Mr Mah Bow Tan | Thank you very much. Sir, let me begin by stating very clearly, in answer to Dr Ong's question, that there is no shift in HDB's mission of providing affordable public hou
24 | SPEECH | 816 | Ms Eunice Elizabeth Olsen | I would like to thank the Minister, and I have two supplementary questions for him.
"""

_REPORT_24068_TITLE = "PROPOSAL TO DEVELOP INTEGRATED RESORTS"
_REPORT_24068_ROWS = """
1 | SPEECH | 731 | Mdm Ho Geok Choo | asked the Minister for Trade and Industry if he will update the House on the progress of the Government's review and deliberation of the various proposals received for th
2 | SPEECH | 775 | Assoc. Prof. Ong Soh Khim | asked the Minister for Trade and Industry (a) whether Government tax revenue is the only economic factor in the assessment of the 19 Integrated Resort (IR) proposals that
3 | SPEECH | 775 | Assoc. Prof. Ong Soh Khim | asked the Minister for Trade and Industry, as much of the scenario planning on the development of an integrated resort and casino are theoretical, (a) will the Government
4 | SPEECH | 739 | Dr Amy Khor Lean Suan (Hong Kah) | Question No. 1, Sir.
5 | SPEECH | 752 | The Minister for Trade and Industry (Mr Lim Hng Kiang) | Mr Speaker, Sir, can I have your permission to take Question Nos. 1 to 3 together as they relate to the same topic?
6 | SPEECH | 702 | Mr Speaker | Yes, you may.
7 | SPEECH | 752 | Mr Lim Hng Kiang | Sir, the Prime Minister will be making a Statement later on on the proposal to develop Integrated Resorts. I would like to urge Members to wait for the Statement. I think
8 | SPEECH | 775 | Assoc. Prof. Ong Soh Khim | asked the Minister for Home Affairs with the development of the Integrated Resort and casino (a) whether there will be an increase in vice, illegal money-lending, money-l
9 | SPEECH | 732 | The Senior Minister of State for Home Affairs (Assoc. Prof. Ho Peng Kee) (for the Minister for Home Affairs) | Sir, I think the Member must have heard the Minister for Trade and Industry. Similarly, the Minister for Home Affairs will be addressing these issues when Members debate
"""

_REPORT_30117_TITLE = "ENVIRONMENT ENFORCEMENT OFFICERS"
_REPORT_30117_ROWS = """
1 | DOCUMENT_TEXT |  |  | 5. To ask the Minister for the Environment whether he is aware that enforcement officers of his Ministry, in the course of their duty, have acted in a very rude and abras
2 | SPEECH | 432 | Mr Chandra Das | Question No. 5, Sir.
3 | SPEECH | 429 | The Minister for the Environment (Dr Ahmad Mattar) | Mr Speaker, Sir, I would like to assure the Member for Potong Pasir, through his proxy, and indeed this House that we will always try to do our best in whatever we do, es
4 | SPEECH | 429 | The Minister for the Environment (Dr Ahmad Mattar) | Sir, public health inspectors are performing a very demanding yet unpleasant job. Being enforcement officers, they can easily become targets of complaints by those whom t
7 | SPEECH | 429 | The Minister for the Environment (Dr Ahmad Mattar) | The following Question stood in the name of Mrs Yu-Foo Yee Shoon -
"""


def _get_role_rows(
    labelled_report: _LabelledReport, role: ParticipantRole
) -> list[tuple[ParticipantRole, ParticipantRoleSource, int, str, Optional[int]]]:
    return [
        participant
        for participant in _summarise_participants(labelled_report.participants)
        if participant[0] == role
    ]


def test_report_22632_member_who_calls_a_question_number_of_a_report_with_no_reader_is_a_reader() -> (
    None
):
    labelled_report = _label_report(_REPORT_22632_TITLE, _REPORT_22632_ROWS)

    assert _get_role_rows(labelled_report, ParticipantRole.READER) == [
        (
            ParticipantRole.READER,
            ParticipantRoleSource.QUESTION_NUMBER_CALL,
            5,
            "Mr Liang Eng Hwa (Holland-Bukit Timah)",
            850,
        )
    ]
    assert _get_person_rows(labelled_report, 850) == [
        (
            ParticipantRole.READER,
            ParticipantRoleSource.QUESTION_NUMBER_CALL,
            5,
            "Mr Liang Eng Hwa (Holland-Bukit Timah)",
            850,
        )
    ]


def test_report_24068_member_who_calls_a_question_number_of_a_report_with_no_reader_is_a_reader() -> (
    None
):
    labelled_report = _label_report(_REPORT_24068_TITLE, _REPORT_24068_ROWS)

    assert _get_role_rows(labelled_report, ParticipantRole.READER) == [
        (
            ParticipantRole.READER,
            ParticipantRoleSource.QUESTION_NUMBER_CALL,
            4,
            "Dr Amy Khor Lean Suan (Hong Kah)",
            739,
        )
    ]


def test_report_30117_member_who_calls_a_number_the_minister_answers_through_his_proxy_is_a_reader() -> (
    None
):
    labelled_report = _label_report(_REPORT_30117_TITLE, _REPORT_30117_ROWS)

    assert _get_person_rows(labelled_report, 432) == [
        (
            ParticipantRole.READER,
            ParticipantRoleSource.QUESTION_NUMBER_CALL,
            2,
            "Mr Chandra Das",
            432,
        )
    ]


_REPORT_43982_TITLE = "Update on Little India Riot"
_REPORT_43982_ROWS = """
1 | PROCEDURAL |  |  | The following question stood in the name of Mr Christopher de Souza –
2 | SPEECH | 918 | Mr Christopher de Souza | 1 To ask the Deputy Prime Minister and Minister for Home Affairs what did the present investigations reveal as the cause of the 8 December 2013 riot and when will the Com
13 | SPEECH | 920 | Ms Denise Phua Lay Peng | asked the Deputy Prime Minister and Minister for Home Affairs whether he will consider developing and implementing a full slew of measures beyond the proposed restriction
23 | SPEECH | 938 | Mr Hri Kumar Nair (Bishan-Toa Payoh) | Question No 1.
24 | SPEECH | 986 | Mr Pritam Singh (Aljunied) | Mdm Speaker, I believe you said you were going to start with Question No 37.
25 | SPEECH | 934 | Mdm Speaker | Yes, as a matter of procedure, we have to mention the questions before that.
26 | SPEECH | 1001 | The Deputy Prime Minister and Minister for Home Affairs (Mr Teo Chee Hean) | Mdm Speaker, I will be making a Ministerial Statement following Question Time. May I have your permission to address the issues that Members have raised in Question Nos 1
27 | SPEECH | 934 | Mdm Speaker | Yes, please, Deputy Prime Minister. Next, Ms Denise Phua, Question No 22?
28 | SPEECH | 920 | Ms Denise Phua Lay Peng (Moulmein-Kallang) | Yes.
"""


def test_report_43982_short_reply_to_the_chairs_call_of_the_next_question_is_no_follow_up() -> (
    None
):
    labelled_report = _label_report(_REPORT_43982_TITLE, _REPORT_43982_ROWS)

    assert _get_person_rows(labelled_report, 920) == [
        (
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            13,
            "Ms Denise Phua Lay Peng",
            920,
        )
    ]


_REPORT_38635_TITLE = "NUMBER OF DETAINEES INTERROGATED SINCE 1-2-63"
_REPORT_38635_ROWS = """
1 | SPEECH | 1349 | Mr David Marshall | asked the Minister for Home Affairs how many persons detained since 1st February, 1963 have already been interrogated by the Special Branch.
2 | SPEECH | 44 | Mr Ong Pang Boon | Mr Speaker, Sir, all the persons detained have had statements taken from them. Because of the number of detainees and the availability of a limited number of skilled inte
3 | SPEECH | 1349 | Mr David Marshall | One-third? I am sorry, Sir. There is a little confusion. I understood the Minister to say that all of them have been interrogated. Is that inaccurate, Sir?
4 | SPEECH | 1352 | Mr Speaker | Perhaps the Minister would like to repeat the answer.
5 | SPEECH | 44 | Mr Ong Pang Boon | Mr Speaker, Sir, all the persons detained have had statements taken from them.
6 | SPEECH | 1349 | Mr David Marshall | Have had?
7 | SPEECH | 44 | Mr Ong Pang Boon | Statements only taken from them. But the actual number of persons who have been fully interrogated is only one-third.
8 | SPEECH | 1349 | Mr David Marshall | Can I ask a supplementary question to that? Are the one-third whose interrogation is completed now allowed access to newspapers and books?
9 | SPEECH | 44 | Mr Ong Pang Boon | Mr Speaker, Sir, I think since 28th March reading materials have been allowed to all detainees.
10 | SPEECH | 1349 | Mr David Marshall | Newspapers?
11 | SPEECH | 1350 | Tun Lim Yew Hock | No, the Petir.
12 | SPEECH | 44 | Mr Ong Pang Boon | Mr Speaker, Sir, reading materials as brought by the detainees' families.
"""

_REPORT_39160_TITLE = "CENTRAL PROVIDENT FUND ORDINANCE"
_REPORT_39160_ROWS = """
1 | SPEECH | 1349 | Mr David Marshall | asked the Minister for Labour whether he will consider introducing legislation to amend the Central Provident Fund Ordinance to enable a contributor to withdraw the amoun
2 | SPEECH | 1358 | The Minister for Labour (Inche Ahmad Bin Ibrahim) | Mr Speaker, Sir, the sole object of the Central Provident Fund Ordinance was to set up a fund to make provision for employees in their old age. The fund was not meant to
3 | SPEECH | 1349 | Mr David Marshall | Mr Speaker, Sir, could we not assist these people? Because if we do not, they will not reach old age to reap it. They will die of starvation. Let a little humanity be int
4 | SPEECH | 1358 | Inche Ahmad Bin Ibrahim | Mr Speaker, Sir, I do not think anybody is going to die of starvation, as claimed by the Member for Anson. In my opinion, the proper way to help the unemployed is not to
5 | SPEECH | 4 | Mr Bani | You will have it.
6 | SPEECH | 1358 | Inche Ahmad Bin Ibrahim | Since the Member for Thomson is very keen on this thing, let me inform him and other Members of the Assembly that my colleague, the Minister for Finance, has told me this
7 | SPEECH | 1350 | Tun Lim Yew Hock (Cairnhill) | Sir, does the Minister consider that the trade union leaders referred to by him truly represent the trade union movement of Singapore?
8 | SPEECH | 1358 | Inche Ahmad Bin Ibrahim | I think, Mr Speaker, the trade union leaders referred to by the Member for Cairnhill will themselves have to answer this. It is not for me to tell him.
9 | SPEECH | 1349 | Mr David Marshall | I am grateful to the Minister for the information he has given, Sir. I am very happy indeed that there is such a scheme in mind. Having put it to the trade union movement
10 | SPEECH | 1358 | Inche Ahmad Bin Ibrahim | Sir, the Government, as the Prime Minister has said, is trying to do everything possible and when the appropriate time comes, we will do it.
11 | SPEECH | 4 | Mr Bani | The Minister has quite conveniently disclosed only the part that is useful to him for the purposes of whatever he has been doing. But I wonder if the Minister would be fa
12 | SPEECH | 1352 | Mr Speaker | Order. Perhaps the question could be worded in such a way as to ask the Minister whether he will table a White Paper. I do not think this House can be detained as long as
13 | SPEECH | 4 | Mr Bani | All that I want to say is that if the Government wants it, we are prepared to disclose the facts to the public.
14 | SPEECH | 10 | Mr Chan Sun Wing (Upper Serangoon) | Mr Speaker, Sir, according to what the Minister for Labour has said, he is trying to put the blame on the trade union leaders for the non-establishment of the unemploymen
21 | SPEECH | 1374 | Dr Sheng Nam Chin | On a point of order, Sir. Mr Speaker, Sir, we are not very fluent in Malay as yet over here - we hope we shall be in a year's time - but it so happens that one of our ear
"""


def test_report_38635_member_whose_only_row_after_the_answer_is_a_short_interjection_is_unlabelled() -> (
    None
):
    labelled_report = _label_report(_REPORT_38635_TITLE, _REPORT_38635_ROWS)

    assert _get_person_rows(labelled_report, 1350) == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            11,
            "Tun Lim Yew Hock",
            1350,
        )
    ]


def test_report_39160_member_whose_only_row_after_the_answer_is_a_point_of_order_is_unlabelled() -> (
    None
):
    labelled_report = _label_report(_REPORT_39160_TITLE, _REPORT_39160_ROWS)

    assert _get_person_rows(labelled_report, 1374) == [
        (
            ParticipantRole.UNLABELLED,
            ParticipantRoleSource.NO_RULE,
            21,
            "Dr Sheng Nam Chin",
            1374,
        )
    ]
    assert _get_person_rows(labelled_report, 4) == [
        (
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
            5,
            "Mr Bani",
            4,
        )
    ]


_REPORT_14331_TITLE = "Annual Water Pipe Leaks in Last Decade"
_REPORT_14331_ROWS = """
1 | SPEECH | 1100 | Mr Leon Perera | asked the Minister for the Environment and Water Resources what is the number of water pipe leaks each year for the past 10 years.
2 | SPEECH | 1065 | The Senior Minister of State for the Environment and Water Resources (Dr Amy Khor Lean Suan) (for the Minister for the Environment and Water Resources) | Mr Deputy Speaker, the Public Utilities Board (PUB) operates a 5,500-kilometre network of pipes to deliver water to 1.5 million customer accounts. Over the last seven yea
9 | SPEECH |  | Mr Deputy Speaker | Does the Member still have supplementary questions after such a long reply?
10 | SPEECH | 1100 | Mr Leon Perera (Non-Constituency Member) | Just a few, Mr Deputy Speaker.
"""

_REPORT_11981_TITLE = (
    "Update on Enforcement and Other Measures after Ban of PMDs on Footpaths"
)
_REPORT_11981_ROWS = """
1 | SPEECH | 1127 | Mr Zainal Sapari | asked the Minister for Transport given the ban on users of personal mobility devices from all footpaths, whether there are plans to distinguish the different types of pub
4 | SPEECH | 1037 | Mr Dennis Tan Lip Fong | asked the Minister for Transport whether the Government has committed additional resources to police the ban of PMDs from footpaths from January 2020 such that the public
5 | SPEECH | 1037 | Mr Dennis Tan Lip Fong | asked the Minister for Transport in light of some food delivery riders switching from e-scooters to electric bikes (a) whether the Government is putting in place addition
6 | SPEECH | 1070 | The Senior Minister of State for Transport (Dr Lam Pin Min) (for the Minister for Transport) | Mr Deputy Speaker, may I have your permission to take Question Nos 5 to 9 together?
7 | SPEECH |  | Mr Deputy Speaker | Yes, please proceed.
20 | SPEECH |  | Mr Deputy Speaker | Mr Ang Wei Neng.
21 | SPEECH | 1021 | Mr Ang Wei Neng (Jurong) | Deputy Speaker, Sir, I thank the Senior Minister of State for the comprehensive reply. I just want to ask a few supplementary questions. He mentioned about 3,000, if I ca
"""


def test_report_14331_unlinked_chair_row_gets_its_office_from_the_label() -> None:
    labelled_report = _label_report(_REPORT_14331_TITLE, _REPORT_14331_ROWS)

    assert [
        participant
        for participant in _summarise_office_marks(labelled_report.participants)
        if participant[0] == ParticipantRole.CHAIR
    ] == [
        (
            ParticipantRole.CHAIR,
            None,
            None,
            "Mr Deputy Speaker",
            OfficeClass.OTHER,
            OfficeSource.LABEL_IN_REPORT,
        )
    ]


def test_report_11981_unlinked_chair_row_gets_its_office_from_the_label() -> None:
    labelled_report = _label_report(_REPORT_11981_TITLE, _REPORT_11981_ROWS)

    assert [
        participant
        for participant in _summarise_office_marks(labelled_report.participants)
        if participant[0] == ParticipantRole.CHAIR
    ] == [
        (
            ParticipantRole.CHAIR,
            None,
            None,
            "Mr Deputy Speaker",
            OfficeClass.OTHER,
            OfficeSource.LABEL_IN_REPORT,
        )
    ]


_REPORT_39956_TITLE = "VISIT OF DUKE OF EDINBURGH"
_REPORT_39956_ROWS = """
3 | DOCUMENT_TEXT |  |  | The following question for oral answer stood on the Order Paper of 4th March, 1959:-
5 | DOCUMENT_TEXT |  |  | "Inche AHMAD BIN IBRAHIM: To ask the Minister for Education how many (i) primary, and (ii) secondary school students were asked to line the route taken by the Duke of Edinburgh from Clifford Pier to Government House on S
6 | DOCUMENT_TEXT |  |  | The Assistant Minister for Education (Inche Mohamed Sidik Bin Haji Abdul Hamid), who was to have answered the question, was absent when the question was called, and has supplied the following answer:-
7 | DOCUMENT_TEXT |  |  | The answers to the first part of the question are:-
10 | DOCUMENT_TEXT |  |  | The answer to the second part of the question is that there was no compulsion, implied or otherwise, for the children to line the route taken by the Duke of Edinburgh. The number from each school represented was necessar
"""


def test_report_39956_answer_supplied_by_an_absent_minister_is_not_asked_aloud() -> (
    None
):
    labelled_report = _label_report(_REPORT_39956_TITLE, _REPORT_39956_ROWS)

    assert labelled_report.participants == []
    assert _summarise_states(labelled_report.states) == [
        (
            QuestionState.NOT_ASKED_ALOUD,
            "The Assistant Minister for Education (Inche Mohamed Sidik Bin Haji Abdul Hamid), who was to have answered the question, was absent when the question was called, and has supplied the following answer:-",
            6,
        )
    ]
