from datetime import datetime

PRESIDING_OFFICERS: dict[tuple[str, int], str] = {
    ("SPEAKER", 0): "George Oehlers",
    ("SPEAKER", 1): "George Oehlers",
    ("SPEAKER", 2): "Coomaraswamy, P.",
    ("SPEAKER", 3): "Yeoh Ghim Seng",
    ("SPEAKER", 4): "Yeoh Ghim Seng",
    ("SPEAKER", 5): "Yeoh Ghim Seng",
    ("SPEAKER", 6): "Yeoh Ghim Seng",
    ("DEPUTY SPEAKER", 6): "Tan Soo Khoon",
    ("SPEAKER", 7): "Tan Soo Khoon",
    ("SPEAKER", 8): "Tan Soo Khoon",
    ("SPEAKER", 9): "Tan Soo Khoon",
    ("SPEAKER", 10): "Abdullah Bin Tarmugi",
    ("DEPUTY SPEAKER", 10): "Chew Heng Ching",
    ("SPEAKER", 11): "Abdullah Bin Tarmugi",
    ("SPEAKER", 12): "Michael Palmer",
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
