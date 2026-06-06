from datetime import datetime

PRESIDING_OFFICERS: dict[tuple[str, int], str] = {
    ("SPEAKER", 0): "George Oehlers",
    ("SPEAKER", 1): "George Oehlers",
    ("SPEAKER", 2): "Coomaraswamy, P.",
    ("SPEAKER", 3): "Yeoh Ghim Seng",
    ("SPEAKER", 4): "Yeoh Ghim Seng",
    ("SPEAKER", 5): "Yeoh Ghim Seng",
    ("SPEAKER", 6): "Yeoh Ghim Seng",
    # Deputy Speakers by parliament term.
    # Parliament 0 (colonial LA 1955-1965): A.P. Rajah held the role throughout.
    # His Speaker-table entry is parliament 1; _resolve_presiding_officer checks
    # (role, 0) before the colonial fallback so this is not overridden by the
    # parliament-1 deputy speaker (Yong Nyuk Lin).
    ("DEPUTY SPEAKER", 0): "A.P. Rajah",
    # Parliament 3 is deliberately omitted: 3 is in COLONIAL_PARLIAMENT_FALLBACKS
    # [1, 2, 3], so adding an entry would redirect all parliament-0 "Mr Deputy Speaker"
    # rows to Yong Nyuk Lin instead of A.P. Rajah. Only 5 rows are affected in
    # parliament 3, so skipping is the correct trade-off.
    ("DEPUTY SPEAKER", 4): "Yong Nyuk Lin",
    ("DEPUTY SPEAKER", 5): "Tan Soo Khoon",
    ("DEPUTY SPEAKER", 6): "Tan Soo Khoon",
    ("SPEAKER", 7): "Tan Soo Khoon",
    ("DEPUTY SPEAKER", 7): "Chew Heng Ching",
    ("SPEAKER", 8): "Tan Soo Khoon",
    ("DEPUTY SPEAKER", 8): "Chew Heng Ching",
    ("SPEAKER", 9): "Tan Soo Khoon",
    ("DEPUTY SPEAKER", 9): "Chew Heng Ching",
    ("SPEAKER", 10): "Abdullah Bin Tarmugi",
    ("DEPUTY SPEAKER", 10): "Chew Heng Ching",
    ("SPEAKER", 11): "Abdullah Bin Tarmugi",
    ("DEPUTY SPEAKER", 11): "Charles Chong",
    ("SPEAKER", 12): "Michael Palmer",
    ("DEPUTY SPEAKER", 12): "Charles Chong",
}

ROLE_ONLY_SPEAKERS: dict[tuple[str, int], str] = {
    ("The Prime Minister", 0): "Lee Kuan Yew",
    ("The Prime Minister", 1): "Lee Kuan Yew",
    ("The Prime Minister", 2): "Lee Kuan Yew",
    ("The Prime Minister", 3): "Lee Kuan Yew",
    ("The Prime Minister", 5): "Lee Kuan Yew",
    ("The Prime Minister", 6): "Lee Kuan Yew",
    ("The Prime Minister", 8): "Goh Chok Tong",
    ("The Prime Minister", 11): "Lee Hsien Loong",
    ("The Minister for Health", 11): "Khaw Boon Wan",
}

NON_SPEAKERS: set[str] = {
    "An hon. Member",
    "Some hon. Members",
    "Non-Residents",
    "Tributes by Leader of the House and Opposition Leaders",
}

COLONIAL_PARLIAMENT_FALLBACKS: list[int] = [1, 2, 3]

# David Marshall was CM until 1956-06-06; Lim Yew Hock from 1956-06-07.
CHIEF_MINISTER_CUTOFF: datetime = datetime(1956, 6, 7)
