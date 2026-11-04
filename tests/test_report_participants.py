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
        read_inline_speakers(speech_asker_rows, (inline_label_to_speaker_id or {}).get),
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
