import json
from typing import Optional

import pytest

from crud.sitting import SittingAttendanceTextRow
from database.speaker import Speaker
from enums import OfficeClass
from services.attendance import (
    EntryOffice,
    build_speaker_lookups,
    get_entry_office,
    get_sitting_entry_offices,
    split_entry_line,
)
from utils.office import (
    HeaderEntry,
    get_answering_for_printed,
    get_header_entries,
    get_label_office,
    get_office_class,
    is_government_office,
)

_GLUED_LINE_SITTING_5847 = (
    "BG Lee Hsien Loong (Ang Mo Kio GRC), Deputy Prime Minister, Prime Minister's Office "
    "Mr Lee Kuan Yew (Tanjong Pagar GRC), Senior Minister, Prime Minister's Office.   "
)

_ENTRY_OFFICE_CASES = [
    pytest.param(
        "Mr Ch'ng Jit Koon (Bukit Merah), Senior Minister of State, Ministry of Community Development.   ",
        "Senior Minister of State, Ministry of Community Development",
        id="sitting_5847_1995_senior_minister_of_state_with_ministry",
    ),
    pytest.param(
        "Mr Foo Cexiang (Tanjong Pagar), Minister of State for Manpower, and Energy, Trade and Industry. ",
        "Minister of State for Manpower, and Energy, Trade and Industry",
        id="sitting_7522_2026_list_minister_of_state_with_commas",
    ),
    pytest.param(
        "Mr Punch Coomaraswamy, Deputy Speaker.   ",
        "Deputy Speaker",
        id="sitting_6322_1966_deputy_speaker_without_bracket",
    ),
    pytest.param(
        "Mr Charles Chong (Joo Chiat), Deputy Speaker.",
        "Deputy Speaker",
        id="sitting_5861_2012_bulleted_deputy_speaker_after_bracket",
    ),
    pytest.param(
        "  * Mr Charles Chong (Joo Chiat), Deputy Speaker.",
        "Deputy Speaker",
        id="sitting_5861_2012_bulleted_deputy_speaker",
    ),
    pytest.param(
        "Mr SPEAKER (Mr Abdullah Tarmugi (East Coast)).  ",
        "Mr SPEAKER",
        id="sitting_5771_2006_speaker_entry",
    ),
    pytest.param(
        "Mdm SPEAKER (Mdm Halimah Yacob (Jurong)). ",
        "Mdm SPEAKER",
        id="sitting_5773_2014_list_madam_speaker_entry",
    ),
    pytest.param(
        "  * Mr SPEAKER (Mr Michael Palmer (Punggol East)).",
        "Mr SPEAKER",
        id="sitting_5861_2012_bulleted_speaker_entry",
    ),
    pytest.param(
        "Mr SPEAKER (Mr Tan Soo Khoon (Brickworks GRC).   ",
        "Mr SPEAKER",
        id="sitting_5801_1989_speaker_entry_with_unclosed_bracket",
    ),
    pytest.param(
        "Mr DEPUTY SPEAKER (Mr Chew Heng Ching (East Coast)).  ",
        "Mr DEPUTY SPEAKER",
        id="sitting_6118_2005_deputy_speaker_entry",
    ),
    pytest.param(
        "Mr Speaker (Dr Yeoh Ghim Seng) (Joo Chiat).   ",
        "Mr Speaker",
        id="sitting_6449_1970_speaker_entry_with_constituency_after_the_name",
    ),
    pytest.param(
        "The Honourable Mr SPEAKER (Sir George Oehlers, O.B.E.).   ",
        "The Honourable Mr SPEAKER",
        id="sitting_5872_1959_honourable_speaker_entry",
    ),
    pytest.param(
        "Mr Abdullah Tarmugi (Siglap), First Deputy Speaker.   ",
        "First Deputy Speaker",
        id="sitting_5873_1989_first_deputy_speaker",
    ),
    pytest.param(
        "Mr Lee Kuan Yew (Tanjong Pagar).   ",
        None,
        id="sitting_5872_1959_member_with_no_office",
    ),
    pytest.param(
        "Prof. Wong Lin Ken (Alexandra). **ASSENT TO BILLS PASSED**   ",
        None,
        id="sitting_6726_1968_heading_glued_to_a_member_with_no_office",
    ),
    pytest.param(
        "Dr Toh Chin Chye (Rochore), Minister for Science and Technology. **ASSENT TO BILLS PASSED**   ",
        "Minister for Science and Technology",
        id="sitting_6948_1972_heading_glued_to_a_member_with_an_office",
    ),
    pytest.param(
        "Mr Pritam Singh (Aljunied), Leader of the Opposition. ",
        "Leader of the Opposition",
        id="sitting_7486_2025_list_leader_of_the_opposition",
    ),
    pytest.param(
        "Mr Eric Chua (Queenstown), Senior Parliamentary Secretary to the Minister for Law, and Minister for Social and Family Development. ",
        "Senior Parliamentary Secretary to the Minister for Law, and Minister for Social and Family Development",
        id="sitting_7486_2025_list_senior_parliamentary_secretary_to_two_ministers",
    ),
    pytest.param(
        "Ms Indranee Rajah (Pasir Ris-Changi), Minister, Prime Minister's Office, Second Minister for Finance, and National Development, and Leader of the House. ",
        "Minister, Prime Minister's Office, Second Minister for Finance, and National Development, and Leader of the House",
        id="sitting_7486_2025_list_minister_with_four_offices",
    ),
    pytest.param(
        "The Honourable Tun Lim Yew Hock, S.M.N. (Havelock), Chief Minister and Minister for Labour and Welfare.   ",
        "Chief Minister and Minister for Labour and Welfare",
        id="sitting_5872_1959_chief_minister_entry",
    ),
    pytest.param(
        "Mr Mak Pak Shee (Geylang), Assistant Minister for Labour and Welfare.   ",
        "Assistant Minister for Labour and Welfare",
        id="sitting_5872_1959_assistant_minister_entry",
    ),
]

_LABEL_CASES = [
    pytest.param(
        "The Acting Minister for Education (Higher Education and Skills) (Mr Ong Ye Kung)",
        "The Acting Minister for Education (Higher Education and Skills)",
        None,
        id="report_16113_nested_bracket_in_the_office",
    ),
    pytest.param(
        "The Minister for Education (Higher Education and Skills) and Second Minister for Defence (Mr Ong Ye Kung)",
        "The Minister for Education (Higher Education and Skills) and Second Minister for Defence",
        None,
        id="report_2963_nested_bracket_before_a_second_office",
    ),
    pytest.param(
        "The Second Deputy Prime Minister (Foreign Affairs) (Mr S. Rajaratnam)",
        "The Second Deputy Prime Minister (Foreign Affairs)",
        None,
        id="report_29225_second_deputy_prime_minister_with_portfolio_bracket",
    ),
    pytest.param(
        "The Senior Parliamentary Secretary to the Minister for Home Affairs (Ms Sun Xueling) (for the Minister for Home Affairs)",
        "The Senior Parliamentary Secretary to the Minister for Home Affairs",
        "for the Minister for Home Affairs",
        id="report_11538_name_bracket_then_for_bracket",
    ),
    pytest.param(
        "The Senior Minister of State for Trade and Industry (Dr Koh Poh Koon) (for the Minister for Trade and Industry (Trade))",
        "The Senior Minister of State for Trade and Industry",
        "for the Minister for Trade and Industry (Trade)",
        id="report_14019_for_bracket_with_nested_bracket",
    ),
    pytest.param(
        "The Parliamentary Secretary to the Ministers for Education (Assoc Prof Dr Muhammad Faishal Ibrahim) (for the Minister for Education (Higher Education and Skills))",
        "The Parliamentary Secretary to the Ministers for Education",
        "for the Minister for Education (Higher Education and Skills)",
        id="report_15209_for_bracket_naming_a_portfolio",
    ),
    pytest.param(
        "The Senior Minister of State for Health (Mr Tan Kiat How)(forthe Coordinating Minister for Social Policies andMinister for Health)",
        "The Senior Minister of State for Health",
        "forthe Coordinating Minister for Social Policies andMinister for Health",
        id="report_50911_glued_forthe_bracket",
    ),
    pytest.param(
        "The Second Minister for National Development (Ms Indranee Rajah) (for theMinister for National Development)",
        "The Second Minister for National Development",
        "for theMinister for National Development",
        id="report_5624_glued_for_theminister_bracket",
    ),
    pytest.param(
        "The Senior Parliamentary Secretary to the Minister for Law (Ms Rahayu Mahzam) (for Minister for Law)",
        "The Senior Parliamentary Secretary to the Minister for Law",
        "for Minister for Law",
        id="report_3303_for_bracket_without_the",
    ),
    pytest.param(
        "The Minister of State for Home Affairs (Mr Desmond Tan) (on behalf of the Minister for Home Affairs and Law)",
        "The Minister of State for Home Affairs",
        "on behalf of the Minister for Home Affairs and Law",
        id="report_11034_on_behalf_of_bracket",
    ),
    pytest.param(
        "Mr Tharman Shanmugaratnam (for the Prime Minister)",
        None,
        "for the Prime Minister",
        id="report_4111_bare_name_for_the_prime_minister",
    ),
    pytest.param(
        "Mr Chan Chee Seng (On behalf of the Minister for Home Affairs)",
        None,
        "On behalf of the Minister for Home Affairs",
        id="report_33396_bare_name_with_capital_on_behalf",
    ),
    pytest.param(
        "Mr A. J. Braga (on behalf of the Minister for Labour and Welfare, Dr Lim Yew Hock)",
        None,
        "on behalf of the Minister for Labour and Welfare, Dr Lim Yew Hock",
        id="report_40323_on_behalf_of_bracket_naming_the_minister",
    ),
    pytest.param(
        "The Minister for Law (Mr K Shanmugam)",
        "The Minister for Law",
        None,
        id="report_2590_office_and_name",
    ),
    pytest.param(
        "The Prime Minister", "The Prime Minister", None, id="report_22779_bare_office"
    ),
    pytest.param(
        "The Leader of the House (Ms Indranee Rajah)",
        "The Leader of the House",
        None,
        id="report_192_leader_of_the_house",
    ),
    pytest.param(
        "The Government Whip (Dr Janil Puthucheary)",
        "The Government Whip",
        None,
        id="report_4677_government_whip",
    ),
    pytest.param("Mr K Shanmugam", None, None, id="report_8_bare_name"),
    pytest.param("Ms Sun Xueling", None, None, id="report_262_bare_name_with_ms"),
    pytest.param(
        "Ms Denise Phua Lay Peng (Jalan Besar)",
        None,
        None,
        id="report_161_constituency_bracket_is_not_an_office",
    ),
    pytest.param("Mr Speaker", "Mr Speaker", None, id="report_1_mr_speaker"),
    pytest.param("Mdm Speaker", "Mdm Speaker", None, id="report_2963_mdm_speaker"),
    pytest.param(
        "Mr Deputy Speaker",
        "Mr Deputy Speaker",
        None,
        id="report_383_mr_deputy_speaker",
    ),
    pytest.param(
        "Mdm Deputy Speaker",
        "Mdm Deputy Speaker",
        None,
        id="report_219_mdm_deputy_speaker",
    ),
    pytest.param("The Chairman", "The Chairman", None, id="report_121_the_chairman"),
    pytest.param(
        "Dr Yeoh Ghim Seng (Mr Speaker)",
        "Mr Speaker",
        None,
        id="report_33144_name_then_speaker_bracket",
    ),
]

_HEADER_CASES = [
    pytest.param(
        " Mr Lee Yock Suan (Minister for Education); Dr Kanwaljit Soin;  ",
        [
            HeaderEntry("Mr Lee Yock Suan", "Minister for Education"),
            HeaderEntry("Dr Kanwaljit Soin", None),
        ],
        id="report_28423_parliament_8_name_then_office_bracket",
    ),
    pytest.param(
        " Mr Chan Chee Seng (Parliamentary Secretary to the Minister for Social Affairs); Mr Ng Yeow Chong; Mr P. Coomaraswam (Mr Speaker);  ",
        [
            HeaderEntry(
                "Mr Chan Chee Seng",
                "Parliamentary Secretary to the Minister for Social Affairs",
            ),
            HeaderEntry("Mr Ng Yeow Chong", None),
            HeaderEntry("Mr P. Coomaraswam", "Mr Speaker"),
        ],
        id="report_36836_parliament_2_speaker_bracket",
    ),
    pytest.param(
        " BG Lee Hsien Loong (Minister of State for Defence and Minister of State for Trade and Industry); Dr Lau Teik Soon; Mr Yeo Choo Kok;  ",
        [
            HeaderEntry(
                "BG Lee Hsien Loong",
                "Minister of State for Defence and Minister of State for Trade and Industry",
            ),
            HeaderEntry("Dr Lau Teik Soon", None),
            HeaderEntry("Mr Yeo Choo Kok", None),
        ],
        id="report_32353_parliament_6_two_offices_in_one_bracket",
    ),
    pytest.param(
        " Mr E. B. David (Chief Secretary); Mr Lee Choon Eng;  ",
        [
            HeaderEntry("Mr E. B. David", "Chief Secretary"),
            HeaderEntry("Mr Lee Choon Eng", None),
        ],
        id="report_34731_parliament_0_chief_secretary",
    ),
    pytest.param(
        " Cdre (Res) Teo Chee Hean(Minister of State for Finance); Dr Toh Keng Kiat;  ",
        [
            HeaderEntry("Cdre (Res) Teo Chee Hean", "Minister of State for Finance"),
            HeaderEntry("Dr Toh Keng Kiat", None),
        ],
        id="report_29330_parliament_8_title_bracket_before_the_name",
    ),
    pytest.param(
        " Dr Amy Khor Lean Suan;The Minister for Community Development, Youth and Sports (Dr Vivian Balakrishnan)  ",
        [
            HeaderEntry("Dr Amy Khor Lean Suan", None),
            HeaderEntry(
                "Dr Vivian Balakrishnan",
                "The Minister for Community Development, Youth and Sports",
            ),
        ],
        id="report_23907_parliament_10_office_then_name_bracket",
    ),
    pytest.param(
        " Dr Lily Neo (Jalan Besar);Mdm Ho Geok Choo;Mdm Ho Geok Choo (West Coast);Mr Low Thia Khiang (Hougang);Mr Abdullah Tarmugi (Mr Speaker);Ms Sylvia Lim (Non-Constituency Member);The Minister for Trade and Industry (Mr Lim Hng Kiang)  ",
        [
            HeaderEntry("Dr Lily Neo", None),
            HeaderEntry("Mdm Ho Geok Choo", None),
            HeaderEntry("Mdm Ho Geok Choo", None),
            HeaderEntry("Mr Low Thia Khiang", None),
            HeaderEntry("Mr Abdullah Tarmugi", "Mr Speaker"),
            HeaderEntry("Ms Sylvia Lim", None),
            HeaderEntry("Mr Lim Hng Kiang", "The Minister for Trade and Industry"),
        ],
        id="report_43290_parliament_11_constituency_speaker_and_office_first",
    ),
    pytest.param(
        " Dr Fatimah Lateef (Marine Parade);Dr Lim Wee Kiak;Dr Lim Wee Kiak (Sembawang);Mdm Halimah Yacob (Jurong);RAdm [NS] Lui Tuck Yew;The Minister of State for Education (RAdm (NS) Lui Tuck Yew)  ",
        [
            HeaderEntry("Dr Fatimah Lateef", None),
            HeaderEntry("Dr Lim Wee Kiak", None),
            HeaderEntry("Dr Lim Wee Kiak", None),
            HeaderEntry("Mdm Halimah Yacob", None),
            HeaderEntry("RAdm [NS] Lui Tuck Yew", None),
            HeaderEntry(
                "RAdm (NS) Lui Tuck Yew", "The Minister of State for Education"
            ),
        ],
        id="report_23047_parliament_11_title_bracket_inside_the_name_bracket",
    ),
    pytest.param(
        " Er Lee Bee Wah (Ang Mo Kio);Mdm Cynthia Phua (Aljunied);Miss Penny Low;Mr Lim Hng Kiang (for the Senior Minister);Mr Abdullah Tarmugi (Mr Speaker)  ",
        [
            HeaderEntry("Er Lee Bee Wah", None),
            HeaderEntry("Mdm Cynthia Phua", None),
            HeaderEntry("Miss Penny Low", None),
            HeaderEntry("Mr Lim Hng Kiang", None),
            HeaderEntry("Mr Abdullah Tarmugi", "Mr Speaker"),
        ],
        id="report_43379_parliament_11_for_bracket_is_not_an_office",
    ),
    pytest.param(
        " Mr Teo Siong Seng, The Deputy Prime Minister and Minister for Home Affairs (Mr Teo Chee Hean)  ",
        [
            HeaderEntry("Mr Teo Siong Seng", None),
            HeaderEntry(
                "Mr Teo Chee Hean",
                "The Deputy Prime Minister and Minister for Home Affairs",
            ),
        ],
        id="report_43659_parliament_12_comma_before_the",
    ),
    pytest.param(
        " Ms Sylvia Lim, Asst Prof Tan Kheng Boon Eugene, The Minister for Law (Mr K Shanmugam), Mr Speaker, Mr Low Thia Khiang (Aljunied)  ",
        [
            HeaderEntry("Ms Sylvia Lim", None),
            HeaderEntry("Asst Prof Tan Kheng Boon Eugene", None),
            HeaderEntry("Mr K Shanmugam", "The Minister for Law"),
            HeaderEntry("Mr Speaker", None),
            HeaderEntry("Mr Low Thia Khiang", None),
        ],
        id="report_20069_parliament_12_comma_before_each_title",
    ),
    pytest.param(
        " Er Dr Lee Bee Wah, The Minister for Health (Mr Gan Kim Yong), Mr Speaker  ",
        [
            HeaderEntry("Er Dr Lee Bee Wah", None),
            HeaderEntry("Mr Gan Kim Yong", "The Minister for Health"),
            HeaderEntry("Mr Speaker", None),
        ],
        id="report_20359_parliament_12_er_dr_title",
    ),
]

_TOP_ATTENDANCE_OFFICE_CLASS_CASES = [
    pytest.param("Deputy Speaker", OfficeClass.OTHER, id="attendance_top_01"),
    pytest.param("Mr SPEAKER", OfficeClass.OTHER, id="attendance_top_02"),
    pytest.param("Prime Minister", OfficeClass.PRIME_MINISTER, id="attendance_top_03"),
    pytest.param(
        "Minister for Education", OfficeClass.MINISTER, id="attendance_top_04"
    ),
    pytest.param("Minister for Finance", OfficeClass.MINISTER, id="attendance_top_05"),
    pytest.param("Minister for Health", OfficeClass.MINISTER, id="attendance_top_06"),
    pytest.param(
        "Minister for Trade and Industry", OfficeClass.MINISTER, id="attendance_top_07"
    ),
    pytest.param(
        "Minister for Foreign Affairs", OfficeClass.MINISTER, id="attendance_top_08"
    ),
    pytest.param("Deputy Government Whip", OfficeClass.OTHER, id="attendance_top_09"),
    pytest.param(
        "Senior Minister, Prime Minister's Office",
        OfficeClass.MINISTER,
        id="attendance_top_10",
    ),
    pytest.param("Minister for Defence", OfficeClass.MINISTER, id="attendance_top_11"),
    pytest.param(
        "Minister for National Development",
        OfficeClass.MINISTER,
        id="attendance_top_12",
    ),
    pytest.param(
        "Parliamentary Secretary to the Minister for National Development",
        OfficeClass.PARLIAMENTARY_SECRETARY,
        id="attendance_top_13",
    ),
    pytest.param(
        "Minister, Prime Minister's Office",
        OfficeClass.MINISTER,
        id="attendance_top_14",
    ),
    pytest.param(
        "Parliamentary Secretary to the Minister for Education",
        OfficeClass.PARLIAMENTARY_SECRETARY,
        id="attendance_top_15",
    ),
    pytest.param(
        "Minister of State, Prime Minister's Office",
        OfficeClass.MINISTER_OF_STATE,
        id="attendance_top_16",
    ),
    pytest.param("Minister", OfficeClass.MINISTER, id="attendance_top_17"),
    pytest.param(
        "Senior Minister of State, Ministry of Education",
        OfficeClass.SENIOR_MINISTER_OF_STATE,
        id="attendance_top_18",
    ),
    pytest.param(
        "Minister of State, Ministry of Defence",
        OfficeClass.MINISTER_OF_STATE,
        id="attendance_top_19",
    ),
    pytest.param("Minister for Labour", OfficeClass.MINISTER, id="attendance_top_20"),
    pytest.param(
        "Parliamentary Secretary to the Minister for Culture",
        OfficeClass.PARLIAMENTARY_SECRETARY,
        id="attendance_top_21",
    ),
    pytest.param(
        "Minister of State for Culture, Community and Youth and Trade and Industry",
        OfficeClass.MINISTER_OF_STATE,
        id="attendance_top_22",
    ),
    pytest.param(
        "Parliamentary Secretary to the Minister for Foreign Affairs",
        OfficeClass.PARLIAMENTARY_SECRETARY,
        id="attendance_top_23",
    ),
    pytest.param(
        "Senior Minister of State, Prime Minister's Office",
        OfficeClass.SENIOR_MINISTER_OF_STATE,
        id="attendance_top_24",
    ),
    pytest.param(
        "Senior Minister of State, Ministry of Foreign Affairs",
        OfficeClass.SENIOR_MINISTER_OF_STATE,
        id="attendance_top_25",
    ),
    pytest.param(
        "Minister for the Environment", OfficeClass.MINISTER, id="attendance_top_26"
    ),
    pytest.param(
        "Deputy Prime Minister and Minister for Finance",
        OfficeClass.DEPUTY_PRIME_MINISTER,
        id="attendance_top_27",
    ),
    pytest.param(
        "Minister for Home Affairs and Leader of the House",
        OfficeClass.MINISTER,
        id="attendance_top_28",
    ),
    pytest.param(
        "Minister of State, Ministry of Education",
        OfficeClass.MINISTER_OF_STATE,
        id="attendance_top_29",
    ),
    pytest.param(
        "Senior Minister of State for Defence",
        OfficeClass.SENIOR_MINISTER_OF_STATE,
        id="attendance_top_30",
    ),
    pytest.param(
        "Minister for Home Affairs and Law",
        OfficeClass.MINISTER,
        id="attendance_top_31",
    ),
    pytest.param(
        "Minister for Law and Minister for Foreign Affairs",
        OfficeClass.MINISTER,
        id="attendance_top_32",
    ),
    pytest.param(
        "Minister for Communications", OfficeClass.MINISTER, id="attendance_top_33"
    ),
    pytest.param(
        "Senior Parliamentary Secretary to the Minister for Home Affairs",
        OfficeClass.SENIOR_PARLIAMENTARY_SECRETARY,
        id="attendance_top_34",
    ),
    pytest.param(
        "Deputy Prime Minister and Minister for Defence",
        OfficeClass.DEPUTY_PRIME_MINISTER,
        id="attendance_top_35",
    ),
    pytest.param(
        "Parliamentary Secretary to the Minister for Home Affairs",
        OfficeClass.PARLIAMENTARY_SECRETARY,
        id="attendance_top_36",
    ),
    pytest.param(
        "Minister for Transport", OfficeClass.MINISTER, id="attendance_top_37"
    ),
    pytest.param(
        "Minister for the Environment and Water Resources and Minister-in-charge of Muslim Affairs",
        OfficeClass.MINISTER,
        id="attendance_top_38",
    ),
    pytest.param(
        "Senior Minister and Coordinating Minister for National Security",
        OfficeClass.MINISTER,
        id="attendance_top_39",
    ),
    pytest.param(
        "Senior Minister of State, Ministry of Law and Ministry of Home Affairs",
        OfficeClass.SENIOR_MINISTER_OF_STATE,
        id="attendance_top_40",
    ),
]

_TWO_CLASS_OFFICE_CLASS_CASES = [
    pytest.param(
        "Prime Minister and Minister for Finance",
        OfficeClass.PRIME_MINISTER,
        id="sitting_5771_2006_prime_minister_and_minister",
    ),
    pytest.param(
        "Deputy Prime Minister and Minister for Finance",
        OfficeClass.DEPUTY_PRIME_MINISTER,
        id="sitting_6314_2004_deputy_prime_minister_and_minister",
    ),
    pytest.param(
        "Deputy Prime Minister and Coordinating Minister for National Security",
        OfficeClass.DEPUTY_PRIME_MINISTER,
        id="attendance_deputy_prime_minister_and_coordinating_minister",
    ),
    pytest.param(
        "Second Deputy Prime Minister (Foreign Affairs)",
        OfficeClass.DEPUTY_PRIME_MINISTER,
        id="sitting_5767_1981_second_deputy_prime_minister_with_portfolio",
    ),
    pytest.param(
        "Acting Minister for Education (Schools) and Senior Minister of State for Transport",
        OfficeClass.MINISTER,
        id="sitting_5783_2016_list_acting_minister_and_senior_minister_of_state",
    ),
    pytest.param(
        "Acting Minister for Manpower and Senior Minister of State for National Development",
        OfficeClass.MINISTER,
        id="sitting_5814_2013_list_acting_minister_and_senior_minister_of_state",
    ),
    pytest.param(
        "Acting Minister for Community Development and Minister of State, Ministry of the Environment and Minister-in-charge of Muslim Affairs",
        OfficeClass.MINISTER,
        id="sitting_5847_1995_acting_minister_and_minister_of_state",
    ),
    pytest.param(
        "Senior Parliamentary Secretary to the Minister for Law, and Minister for Social and Family Development",
        OfficeClass.SENIOR_PARLIAMENTARY_SECRETARY,
        id="sitting_7486_2025_list_senior_parliamentary_secretary_to_two_ministers",
    ),
    pytest.param(
        "Senior Parliamentary Secretary to the Minister for Culture, Community and Youth, and Minister for Sustainability and the Environment",
        OfficeClass.SENIOR_PARLIAMENTARY_SECRETARY,
        id="sitting_7486_2025_list_senior_parliamentary_secretary_to_ministers_with_commas",
    ),
    pytest.param(
        "Parliamentary Secretary to the Minister for Culture, Community and Youth",
        OfficeClass.PARLIAMENTARY_SECRETARY,
        id="sitting_5769_2018_list_parliamentary_secretary_to_a_ministry_with_commas",
    ),
    pytest.param(
        "Parliamentary Secretary to the Minister for Social Affairs, and Government Whip",
        OfficeClass.PARLIAMENTARY_SECRETARY,
        id="sitting_6104_1965_parliamentary_secretary_and_government_whip",
    ),
    pytest.param(
        "Parliamentary Secretary to the Prime Minister",
        OfficeClass.PARLIAMENTARY_SECRETARY,
        id="sitting_5784_1962_parliamentary_secretary_to_the_prime_minister",
    ),
    pytest.param(
        "Minister of State, Ministry of Labour and Government Whip",
        OfficeClass.MINISTER_OF_STATE,
        id="sitting_5767_1981_minister_of_state_and_government_whip",
    ),
    pytest.param(
        "Minister of State for the Prime Minister's Department",
        OfficeClass.MINISTER_OF_STATE,
        id="sitting_5787_1967_minister_of_state_for_the_prime_ministers_department",
    ),
    pytest.param(
        "Minister for Information, Communications and the Arts and Government Whip",
        OfficeClass.MINISTER,
        id="sitting_5771_2006_minister_and_government_whip",
    ),
]

_OTHER_OFFICE_CLASS_CASES = [
    pytest.param("Mdm SPEAKER", id="sitting_5773_2014_list_madam_speaker"),
    pytest.param("Mr DEPUTY SPEAKER", id="sitting_6118_2005_deputy_speaker"),
    pytest.param("First Deputy Speaker", id="sitting_5873_1989_first_deputy_speaker"),
    pytest.param("The Government Whip", id="report_4677_government_whip_label"),
    pytest.param(
        "Leader of the Opposition", id="sitting_7486_2025_list_leader_of_the_opposition"
    ),
    pytest.param("The Leader of the House", id="report_192_leader_of_the_house_label"),
    pytest.param("Chief Minister", id="header_chief_minister"),
    pytest.param(
        "Assistant Minister for Labour and Welfare",
        id="sitting_5872_1959_assistant_minister",
    ),
    pytest.param("Chief Secretary", id="report_34731_chief_secretary_header"),
    pytest.param("Financial Secretary", id="report_35476_financial_secretary_header"),
    pytest.param("Attorney-General", id="header_attorney_general"),
    pytest.param("Acting Financial Secretary", id="header_acting_financial_secretary"),
]

_GOVERNMENT_OFFICE_CASES = [
    pytest.param("Minister for Education", True, id="attendance_minister"),
    pytest.param("Prime Minister", True, id="attendance_prime_minister"),
    pytest.param(
        "Minister of State, Ministry of Defence",
        True,
        id="attendance_minister_of_state",
    ),
    pytest.param(
        "Parliamentary Secretary to the Minister for Education",
        True,
        id="attendance_parliamentary_secretary",
    ),
    pytest.param(
        "Minister for Home Affairs and Leader of the House",
        True,
        id="sitting_5774_2005_minister_and_leader_of_the_house",
    ),
    pytest.param(
        "The Leader of the House", True, id="report_192_leader_of_the_house_label"
    ),
    pytest.param("Attorney-General", True, id="header_attorney_general"),
    pytest.param("Chief Secretary", True, id="report_34731_chief_secretary_header"),
    pytest.param(
        "Financial Secretary", True, id="report_35476_financial_secretary_header"
    ),
    pytest.param("Chief Minister", True, id="header_chief_minister"),
    pytest.param(
        "Assistant Minister for Labour and Welfare",
        True,
        id="sitting_5872_1959_assistant_minister",
    ),
    pytest.param(
        "Deputy Speaker and Minister of State",
        True,
        id="constructed_deputy_speaker_and_minister_of_state",
    ),
    pytest.param(
        "Minister, Prime Minister's Office",
        True,
        id="attendance_minister_in_the_prime_ministers_office",
    ),
    pytest.param("Deputy Speaker", False, id="attendance_deputy_speaker"),
    pytest.param("Mr SPEAKER", False, id="attendance_speaker_entry"),
    pytest.param("Mr Speaker", False, id="report_1_mr_speaker_label"),
    pytest.param("The Chairman", False, id="report_121_the_chairman_label"),
    pytest.param(
        "Deputy Government Whip", False, id="attendance_deputy_government_whip"
    ),
    pytest.param("The Government Whip", False, id="report_4677_government_whip_label"),
    pytest.param(
        "Leader of the Opposition",
        False,
        id="sitting_7486_2025_list_leader_of_the_opposition",
    ),
    pytest.param(
        "Mayor, South West District", False, id="constructed_mayor_of_a_district"
    ),
]


@pytest.mark.parametrize(("entry_line", "expected_office"), _ENTRY_OFFICE_CASES)
def test_entry_office_is_the_text_after_the_constituency_bracket(
    entry_line: str, expected_office: Optional[str]
) -> None:
    assert get_entry_office(entry_line) == expected_office


def test_sitting_5847_1995_glued_line_gives_each_member_their_own_office() -> None:
    entries = split_entry_line(_GLUED_LINE_SITTING_5847)

    assert [get_entry_office(entry) for entry in entries] == [
        "Deputy Prime Minister, Prime Minister's Office",
        "Senior Minister, Prime Minister's Office",
    ]


@pytest.mark.parametrize(
    ("speaker_label", "expected_office", "expected_answering_for"), _LABEL_CASES
)
def test_label_office_drops_the_name_bracket_and_the_for_bracket(
    speaker_label: str,
    expected_office: Optional[str],
    expected_answering_for: Optional[str],
) -> None:
    assert get_label_office(speaker_label) == expected_office
    assert get_answering_for_printed(speaker_label) == expected_answering_for


@pytest.mark.parametrize(("header", "expected_entries"), _HEADER_CASES)
def test_header_entries_split_on_semicolons_and_on_commas_before_a_title(
    header: str, expected_entries: list[HeaderEntry]
) -> None:
    assert get_header_entries(header) == expected_entries


@pytest.mark.parametrize(
    ("office_printed", "expected_class"), _TOP_ATTENDANCE_OFFICE_CLASS_CASES
)
def test_office_class_of_the_most_common_attendance_offices(
    office_printed: str, expected_class: OfficeClass
) -> None:
    assert get_office_class(office_printed) == expected_class


@pytest.mark.parametrize(
    ("office_printed", "expected_class"), _TWO_CLASS_OFFICE_CLASS_CASES
)
def test_office_class_of_a_text_that_names_two_classes_is_the_highest(
    office_printed: str, expected_class: OfficeClass
) -> None:
    assert get_office_class(office_printed) == expected_class


@pytest.mark.parametrize("office_printed", _OTHER_OFFICE_CLASS_CASES)
def test_office_class_of_a_chair_whip_or_non_ministerial_office_is_other(
    office_printed: str,
) -> None:
    assert get_office_class(office_printed) == OfficeClass.OTHER


@pytest.mark.parametrize(
    ("office_printed", "expected_is_government"), _GOVERNMENT_OFFICE_CASES
)
def test_government_office_names_a_minister_secretary_or_law_officer(
    office_printed: str, expected_is_government: bool
) -> None:
    assert is_government_office(office_printed) is expected_is_government


def _build_sitting_attendance_text_row(
    markdown_content: Optional[str], attendance_list: Optional[str]
) -> SittingAttendanceTextRow:
    return SittingAttendanceTextRow(
        id=1,
        sitting_date="2-4-2025",
        parlement_no=14,
        volume_no=None,
        markdown_content=markdown_content,
        attendance_list=attendance_list,
    )


_ENTRY_OFFICE_LOOKUPS = build_speaker_lookups(
    [
        Speaker(
            name="Chee Hong Tat",
            party="PAP",
            is_legislative_assembly=False,
            parliament_number=14,
        )
    ]
)


def test_markdown_sitting_gives_the_office_of_each_present_and_absent_entry_that_has_one() -> (
    None
):
    markdown_content = (
        "PRESENT:\n"
        "Mr Chee Hong Tat (Bishan-Toa Payoh), Senior Minister of State for Finance.\n"
        "Mr Pritam Singh (Aljunied).\n"
        "ABSENT:\n"
        "Mr Nobody Known (Nowhere), Minister for Health.\n"
    )

    entry_offices = get_sitting_entry_offices(
        _build_sitting_attendance_text_row(markdown_content, None),
        _ENTRY_OFFICE_LOOKUPS,
    )

    assert entry_offices == [
        EntryOffice("Chee Hong Tat", "Senior Minister of State for Finance"),
        EntryOffice("Nobody Known", "Minister for Health"),
    ]


def test_list_sitting_skips_a_leave_note_a_missing_name_and_an_entry_without_an_office() -> (
    None
):
    attendance_list = json.dumps(
        [
            {
                "mpName": "Mr Chee Hong Tat (Bishan-Toa Payoh), Senior Minister of State for Finance. ",
                "attendance": True,
            },
            {"mpName": "Mr Pritam Singh (Aljunied)", "attendance": True},
            {
                "mpName": "For information on permission given to Members for leave of absence, Minister for Health",
                "attendance": False,
            },
            {"mpName": None, "attendance": True},
        ]
    )

    entry_offices = get_sitting_entry_offices(
        _build_sitting_attendance_text_row(None, attendance_list),
        _ENTRY_OFFICE_LOOKUPS,
    )

    assert entry_offices == [
        EntryOffice("Chee Hong Tat", "Senior Minister of State for Finance")
    ]


def test_sitting_with_neither_markdown_nor_a_list_gives_no_entry_offices() -> None:
    assert (
        get_sitting_entry_offices(
            _build_sitting_attendance_text_row(None, None), _ENTRY_OFFICE_LOOKUPS
        )
        == []
    )
