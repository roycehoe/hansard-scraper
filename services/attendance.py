import json
import re
from dataclasses import dataclass
from typing import Optional

from crud.attendance import AttendanceLocationRow
from database.attendance import Attendance
from database.sitting import Sitting
from database.speaker import Speaker
from exceptions import HansardWriteCheckError
from schemas.constituency_names import ConstituencyNames
from schemas.hansard_report_response import HansardReportAttendanceEntry
from utils.names import (
    invert_to_natural,
    normalize_name,
    period_normalize,
    spelling_normalize,
    strip_bin,
    strip_middle_haji,
    strip_title,
)
from utils.sitting_dates import parse_sitting_date
from utils.speaker_terms import SPEAKER_TERMS

# Derived from each sitting's Parliament No header
# NOTE: volumes 1 to 11 print Parliament No 1 in the sitting header, but their reports carry Parliament 0, so they map to 0.
VOLUME_TO_PARLIAMENT: dict[int, int] = {
    1: 0, 2: 0, 3: 0, 4: 0, 6: 0, 7: 0, 8: 0, 9: 0, 11: 0,
    12: 0, 13: 0, 14: 0, 15: 0, 16: 0, 17: 0, 18: 0, 19: 0,
    20: 0, 21: 0, 22: 0, 23: 0,
    24: 1, 25: 1, 26: 1,
    27: 2, 28: 2, 29: 2, 30: 2, 31: 2,
    32: 3, 33: 3, 34: 3, 35: 3,
    36: 4, 37: 4, 38: 4, 39: 4,
    40: 5, 41: 5, 42: 5, 43: 5, 44: 5,
    45: 6, 46: 6, 47: 6, 48: 6, 49: 6, 50: 6, 51: 6,
    52: 7, 53: 7, 54: 7, 55: 7, 56: 7, 57: 7, 58: 7,
    59: 8, 60: 8, 61: 8, 62: 8, 63: 8, 64: 8, 65: 8, 66: 8,
    67: 9, 68: 9, 69: 9, 70: 9, 71: 9, 72: 9, 73: 9,
    74: 10, 75: 10, 76: 10, 77: 10, 78: 10, 79: 10, 80: 10, 81: 10,
    82: 11, 83: 11, 84: 11, 85: 11, 86: 11, 87: 11,
    88: 12, 89: 12,
}

# NOTE: scanner errors made in every parliament go here; fixes that need a parliament go in _NAME_PARLIAMENT_TO_CANONICAL_SPEAKER.
_OCR_FORM_TO_CORRECTED_NAME: dict[str, str] = {
    "lai tha chai": "Lai Tai Chai",  # vols 32-51, parl 3-6
    "lai tha chia": "Lai Tai Chai",
    "chin ham tong": "Chin Harn Tong",
    "lbrahim othman": "Ibrahim Othman",
    "yong nyuk lm": "Yong Nyuk Lin",
    "leong keng sung": "Leong Keng Seng",
    "gob keng swee": "Goh Keng Swee",
    "gob chew chua": "Goh Chew Chua",
    "a rahim lshak": "A. Rahim Ishak",
    "jek youn thong": "Jek Yeun Thong",
    "jek yuen thong": "Jek Yeun Thong",
    "wee loon boon": "Wee Toon Boon",
    "wee toon. boon": "Wee Toon Boon",
    "yaacoh bin mohamed": "Yaacob Bin Mohamed",
    "toh chih chye": "Toh Chin Chye",
    "ng kah tins": "Ng Kah Ting",
    "ho chong choon": "Ho Cheng Choon",
    "ho kah loong": "Ho Kah Leong",
    "lob miaw gong": "Loh Miaw Gong",
    "sia kat hui": "Sia Kah Hui",
    "buang bin omar junied": "Buang Bin Omar Junid",
    "wang soon fong": "Wong Soon Fong",
    "urn cheng lock": "Lim Cheng Lock",
    "sahorah binte ahmad": "Sahorah Binte Ahmat",
    "he puay choc.": "Hoe Puay Choo",
    "scow peck leng": "Seow Peck Leng",
    "tan kb gan": "Tan Kia Gan",
    "ahmed bin ibrahim": "Ahmad Bin Ibrahim",
    "sob ghee soon": "Soh Ghee Soon",
    "low for tuck": "Low Por Tuck",
    "lim yew yock": "Lim Yew Hock",
    "rahmat bin kenap a1-haj": "Rahmat Bin Kenap",
    "haii rahmat bin kenap": "Rahmat Bin Kenap",
    "rahmat bin kensp": "Rahmat Bin Kenap",
    "s rajaratnarn": "S. Rajaratnam",
    "s rajaratam": "S. Rajaratnam",
    "s raiaratnam": "S. Rajaratnam",
    "yaacob bin mohamed al-haj": "Yaacob Bin Mohamed",
    "inche. ahmad jabri bin mohammad akib": "Ahmad Jabri Bin Mohammad Akib",
    "lim kim san. d u t": "Lim Kim San",
    "ho see beng. b b m": "Ho See Beng",
    "lim yew hock. s m n": "Lim Yew Hock",
    "thio chan bee. j p": "Thio Chan Bee",
    "thio chan bee, .j p": "Thio Chan Bee",
    "thio chan bee, j p": "Thio Chan Bee",
    "thio chan bee, j.p.": "Thio Chan Bee",
    "r jumabhoy. c b e": "Jumabhoy, R.",
    "abdul hamid bin haji jumat. p m n": "Abdul Hamid Bin Haji Jumat",
    "ong piah teng. o b e": "Ong Piah Teng",
    "tan eng liang. b b m": "Tan Eng Liang",
    "yeo choc kok": "Yeo Choo Kok",
    "yoo choo kok": "Yeo Choo Kok",
    "chai chong vii": "Chai Chong Yii",
    "ivan batist": "Ivan Baptist",
    "lee yiok song": "Lee Yiok Seng",
    "lee chiaw memg": "Lee Chiaw Meng",
    "mg nam piau": "Ang Nam Piau",
    "lou teik soon": "Lau Teik Soon",  # vol 39, parl 4
    "eugune yap giau cheng": "Eugene Yap Giau Cheng",
    "yeo n ing hong": "Yeo Ning Hong",  # vol 45, parl 6
    "koh kam son": "Koh Lam Son",  # vol 50, parl 6
    "rohan'bin kamis": "Rohan Bin Kamis",  # vols 38-44, parl 4-5
    "p govindasamy": "P. Govindaswamy",  # parl 1-4
    "p govindaswarny": "P. Govindaswamy",
    "n govindaswamy": "N. Govindasamy",  # parl 2-4
    "wong kwei cheong, p bm.": "Wong Kwei Cheong",
    "tay eng soon, p bm.": "Tay Eng Soon",
    "mohd ali bin aiwi": "Mohd Ali Bin Alwi",  # parl 1
    "chiang hal ding": "Chiang Hai Ding",  # vols 30-32, parl 2-3
    "yeo loon chia": "Yeo Toon Chia",  # vols 34-36, parl 3-4
    "scab mui kok": "Seah Mui Kok",  # vols 32-33, parl 3
    "mg kok peng": "Ang Kok Peng",  # vol 33, parl 3
    "sidek bin sa niff": "Sidek Bin Saniff",  # vols 42-45, parl 5-6
    "yeo ni ng hong": "Yeo Ning Hong",
    "francis thomas.": "Francis Thomas",
    "john mammen.": "John Mammen",
    "lnche ahmad jabri bin mohammad akib": "Ahmad Jabri Bin Mohammad Akib",
    "inche, ahmad jabri bin mohammad akib": "Ahmad Jabri Bin Mohammad Akib",
    "oon khye kiang. financial secretary": "Oon Khye Kiang",
    "t m hart, c m g financial secretary": "T.M. Hart",
    "sidek bin siniff": "Sidek Bin Saniff",
    "yea choo kok": "Yeo Choo Kok",
    "goh ghok tong": "Goh Chok Tong",
    "hwang soo tin": "Hwang Soo Jin",
    "othmah bin haron eusofe": "Othman Bin Haron Eusofe",
    "s joyakumar": "S Jayakumar",
    "tsy eng soon": "Tay Eng Soon",
    "lea kuan yew": "Lee Kuan Yew",
    "lau telk soon": "Lau Teik Soon",
    "ho see beng, b bm.": "Ho See Beng",
    "r jumabhoy)": "Jumabhoy, R.",  # parl 1
    "yeoh ghim seng. b b m": "Yeoh Ghim Seng",
    "yeoh ghim seng, b b m, .j p": "Yeoh Ghim Seng",
    "yeoh ghim seng, b b m,. j p": "Yeoh Ghim Seng",
    "p selvedurai": "P. Selvadurai",
    "mold. ariff bin suradi": "Mohd Ariff Bin Suradi, Haji",
    "ow chin. hock": "Ow Chin Hock",  # parl 4-9
    "m k a jabba.r": "M K A Jabbar",  # parl 5
    "mah bow t2an": "Mah Bow Tan",  # parl 7-8
    "said! haji shariff": "Saidi Haji Shariff",
    "saidi haii shariff": "Saidi Haji Shariff",
    "jek yeun thong minister for culture": "Jek Yeun Thong",
    "goh keng swee minister of defence": "Goh Keng Swee",
    "ahmad bin ibrahim (sembawang. minister for labour": "Ahmad Bin Ibrahim",
    "lee kuan yew (tanjong pagan. prime minister": "Lee Kuan Yew",
    "george oehlers. o b e": "George Oehlers",
    "george oehlers, (o b e": "George Oehlers",
    "w a c goode. c m g": "W.A.C. Goode",
    "sha'ari bin tedin": "Sha'ari Bin Tadin",
    "sh'ari bin tadin": "Sha'ari Bin Tadin",
    "s1ia'ari bin tadin": "Sha'ari Bin Tadin",
    "ahmad, bin ibrahim": "Ahmad Bin Ibrahim",
    "j, f conceicao": "J.F. Conceicao",
    "hon sui sen. d u b c": "Hon Sui Sen",
    "chau sik ting, p bm.": "Chau Sik Ting",
    "ho see beng, a.bm.": "Ho See Beng",
    "mohd ghazali bin ismail'": "Mohd Ghazali Bin Ismail",
    "hwang. soo jin": "Hwang Soo Jin",
    "fong. sip chee": "Fong Sip Chee",
    "p seivadurai": "P. Selvadurai",
    "inche. buang bin omar junid": "Buang Bin Omar Junid",
    "j,f conceicao": "J.F. Conceicao",
    "ong piah teng, o b e": "Ong Piah Teng",
    "ang nam piau.": "Ang Nam Piau",
    "yeoh ghim seng)": "Yeoh Ghim Seng",
    "p selvadural": "P. Selvadurai",
    "yaacob bin mohamed ai-haj": "Yaacob Bin Mohamed",
    "hwang soo un": "Hwang Soo Jin",  # parl 2, vol 27
    "lau teik sobn": "Lau Teik Soon",  # parl 5, vol 45
    "mohd mi bin alwi": "Mohd Ali Bin Alwi",  # parl 0, vol 20
    "othman bin haron elisofe": "Othman Bin Haron Eusofe",  # parl 5, vol 45
    "adbul hamid bin haji jumat": "Abdul Hamid Bin Haji Jumat",  # parl 1, vol 14
    "dl chiang hai ding": "Chiang Hai Ding",  # parl 2, vol 32
    "dr yeoh ghim seng": "Yeoh Ghim Seng",  # parl 6, vol 50
    "mr tan soo khoon": "Tan Soo Khoon",  # parl 6, vol 50
    "cha,u sik ting": "Chau Sik Ting",  # parl 5, vol 42
    "lee tee long": "Lee Tee Tong",  # parl 0 to 1, vol 23
    "ch'ng lit koon": "Ch'ng Jit Koon",  # parl 3, vol 32
    "ong tang cheong": "Ong Teng Cheong",  # parl 4, vol 39
    "ong tong cheong": "Ong Teng Cheong",  # parl 5, vol 43
    "lee yock suen": "Lee Yock Suan",  # parl 5, vol 40
    "sia khoon soong": "Sia Khoon Seong",  # parl 4, vol 38
    "lirn choon mong": "Lim Choon Mong",  # parl 1, vol 9
    "lim you eng": "Lin You Eng",  # parl 1, vol 15
    "mt. lin you eng": "Lin You Eng",  # parl 1, vol 14
    "phue bah lee": "Phua Bah Lee",  # parl 5, vol 43
    "phua bali lee": "Phua Bah Lee",  # parl 3, vol 31
    "ang kok peng, b bm.": "Ang Kok Peng",  # parl 5, vol 44
    "ang kok peng. b b m": "Ang Kok Peng",  # parl 3, vol 36
    "seah mui kok, b bm.": "Seah Mui Kok",  # parl 5, vol 43
    "seah mui kok, e.bm.": "Seah Mui Kok",  # parl 5, vol 43
    "seah mui kok, ba.m.": "Seah Mui Kok",  # parl 5, vol 44
    "thio chan bee, j p tanglin)": "Thio Chan Bee",  # parl 1, vol 15
    "c h butterfield. q c": "C.H. Butterfield",  # parl 1, vol 2
    "e p shanks, q c attorney-general": "E.P. Shanks",  # parl 1, vol 6
    "goh keng swee kreta ayer) minister for finance": "Goh Keng Swee",  # parl 0 to 1, vol 23
    "lim kim san cairnhill), minister for national development": "Lim Kim San",  # parl 0 to 1, vol 23
    "chor yeok eng bukit timah), parliamentary secretary to the minister for health": "Chor Yeok Eng",  # parl 3, vol 31
    "ngeow pack hua aboon lay)": "Ngeow Pack Hua",  # parl 4, vol 38
    "ya'acob bin mohamed kampong ubi), minister of state, prime minister's office": "Yaacob Bin Mohamed",  # parl 2, vol 27
    "wong foo nam.": "Wong Foo Nam",  # parl 1, vol 2
    "s v lingam.": "S.V. Lingam",  # parl 1, vol 11
    "c h koh.": "C.H. Koh",  # parl 1, vol 15
    "urn kim san": "Lim Kim San",  # parl 2, vol 30
    "punch coomaraswamy, deputy speaker": "P. Coomaraswamy",  # parl 1, vol 25
    "p coomaraswamy, deputy speaker": "P. Coomaraswamy",  # parl 1, vol 25
    "p coomaraswam": "P. Coomaraswamy",  # 1968 header, parl 2
    "fang kim heng": "Fong Kim Heng",  # 1964 bracket, parl 0
    "absent: mr ahmad mohd magad": "Ahmad Mohd Magad",  # parl 9, vol 70
    # Found in the October 2026 attribution pass
    "wan hussin bin hj zoohri": "Wan Hussin Zoohri",
    "mohamed maliki bin osman": "Mohamad Maliki Bin Osman",
    "rahmat bin kenap al-haj": "Rahmat Bin Kenap",
    "yaacob bin ibrahim": "Yaacob Bin Mohamed",
    "mohd sidik bin haji abdul hamid": "Mohamed Sidik Bin Haji Abdul Hamid",
    "mohdsidik bin haji abdul hamid": "Mohamed Sidik Bin Haji Abdul Hamid",
    "the assistant minister for education inche mohamed sidik bin haji abdul hamid": "Mohamed Sidik Bin Haji Abdul Hamid",
    "baharuddin bin mohd ariff": "Baharuddin Bin Mohamed Ariff",
    "baharuddin": "Baharuddin Bin Mohamed Ariff",
    "mohamed ali bin alwi": "Mohd Ali Bin Alwi",
    "mansor haii sukaimi": "Mansor Haji Sukaimi",
    "ho see bong": "Ho See Beng",
    "hon sui son": "Hon Sui Sen",
    "hon sui san": "Hon Sui Sen",
    "chin tet yuing": "Chin Tet Yung",
    "ling how dong": "Ling How Doong",
    "yu-foo yee soon": "Yu-Foo Yee Shoon",
    "yu-fu yee shoon": "Yu-Foo Yee Shoon",
    "wan soo bee": "Wan Soon Bee",
    "lau ping sun": "Lau Ping Sum",
    "chew heng chin": "Chew Heng Ching",
    "lim hng hiang": "Lim Hng Kiang",
    "matthias yao chi": "Matthias Yao Chih",
    "wong kang seng": "Wong Kan Seng",
    "tan cheng bok": "Tan Cheng Bock",
    "sin boon an": "Sin Boon Ann",
    "chiam seng tong": "Chiam See Tong",
    "seng han tong": "Seng Han Thong",
    "chan chee song": "Chan Chee Seng",
    "arthur beng kin lam": "Arthur Beng Kian Lam",
    "tony tan kong yam": "Tony Tan Keng Yam",
    "ahmad jabri bin mohamad akib": "Ahmad Jabri Bin Mohammad Akib",
    "ang kok pong": "Ang Kok Peng",
    "tan eng hang": "Tan Eng Liang",
    "ellen lee geck hoon": "Ellen Lee",
    "wong lm ken": "Wong Lin Ken",  # parl 2, vol 27
    "phek hoong": "Irene Ng Phek Hoong",  # parl 12, vol 88
    "the hounourable mr a j braga": "Braga, A.J.",  # parl 0, vol 9
    "too chong tee": "Teo Chong Tee",  # parl 4, vol 39
    "tan cheng sen": "Tan Cheng San",  # parl 4, vol 38
    "tay bon too": "Tay Boon Too",  # parl 1, vol 25
    "teh cheang won": "Teh Cheang Wan",
    "wong kan song": "Wong Kan Seng",
    "hon sui sea": "Hon Sui Sen",
    "tang see chum": "Tang See Chim",
    "tan cheng sock": "Tan Cheng Bock",
    "ngeow pack hue": "Ngeow Pack Hua",
    "ong teng choong": "Ong Teng Cheong",
    "lim boon hong": "Lim Boon Heng",
    "yeo ning yong": "Yeo Ning Hong",
    "chiam see chiam": "Chiam See Tong",
}

# NOTE: surname-only forms and inverted canonicals go here; OCR character errors belong in _OCR_FORM_TO_CORRECTED_NAME.
# NOTE: a key of Parliament 0 names a member who sat only in the Legislative Assembly; a key of 1 names one who also sat in Parliament 1.
_NAME_PARLIAMENT_TO_CANONICAL_SPEAKER: dict[tuple[str, int], str] = {
    ("d s marshall", 0): "David Marshall",
    # Mrs Devan Nair, not C. V. Devan Nair
    ("c v devan nair", 1): "Devan Nair, Mrs",
    ("william goode, k c m g", 0): "William Goode",
    ("g e n oehlers", 0): "George Oehlers",
    ("rahamat bin kenap", 1): "Rahmat Bin Kenap",
    ("koo young", 1): "Koo Yong",
    ("chew chin han", 1): "Chew Chin Harn",
    ("hart", 0): "Hart, T.M.",
    ("goode", 0): "Goode, W.A.C.",
    ("butterfield", 0): "Butterfield, C.H.",
    ("shanks", 0): "Shanks, E.P.",
    ("david", 0): "David, E.B.",
    ("sutherland", 0): "Sutherland, G.A.P.",
    ("stewart", 0): "Stewart, S.T.",
    ("davies", 0): "Davies, E.J.",
    ("higham", 0): "Higham, J.D.",
    # NOTE: the Speaker table spells it Gahni
    ("ahmad khalis bin abdul ghani", 10): "Ahmad Khalis bin Abdul Gahni",
    ("masagos zulkifli b m m", 11): "Masagos Zulkifli Bin Masagos Mohamad",
    ("masagos zulkifli b m m", 12): "Masagos Zulkifli Bin Masagos Mohamad",
    ("masagos zulkifli b m m", 13): "Masagos Zulkifli Bin Masagos Mohamad",
    ("masagos zulkifli b m m", 14): "Masagos Zulkifli Bin Masagos Mohamad",
    ("lim chun leng, michael", 8): "Lim Chun Leng, Michael, Dr",
    ("lim chun leng, michael", 9): "Lim Chun Leng, Michael, Dr",
    ("lim chun leng, michael", 10): "Lim Chun Leng, Michael, Dr",
    ("abdul nasser bin kamaruddin", 7): "Abdul Nasser Bin Kamarudin",
    ("seet ai mee", 7): "Seet Ai Mei, Dr",
    ("jeyaretnam", 5): "J B Jeyaretnam",
    ("jeyaretnam", 6): "J B Jeyaretnam",
    ("jeyaretnam", 9): "J B Jeyaretnam",
    ("jayakumar", 5): "S Jayakumar",
    ("jayakumar", 6): "S Jayakumar",
    ("jayakumar", 7): "S Jayakumar",
    ("jayakumar", 8): "S Jayakumar",
    ("jayakumar", 9): "S Jayakumar",
    ("jayakumar", 10): "S Jayakumar",
    ("jayakumar", 11): "S Jayakumar",
    ("dhanabalan", 4): "S. Dhanabalan",
    ("dhanabalan", 5): "S. Dhanabalan",
    ("dhanabalan", 6): "S. Dhanabalan",
    ("dhanabalan", 7): "S. Dhanabalan",
    ("dhanabalan", 8): "S. Dhanabalan",
    ("barker", 1): "Barker, E.W.",
    ("barker", 2): "Barker, E.W.",
    ("barker", 3): "Barker, E.W.",
    ("barker", 4): "Barker, E.W.",
    ("barker", 5): "Barker, E.W.",
    ("barker", 6): "Barker, E.W.",
    ("bani", 1): "Bani, S.T.",
    ("joshua benjamin jeyaretnam", 5): "J B Jeyaretnam",
    ("joshua benjamin jeyaretnam", 6): "J B Jeyaretnam",
    ("ya'acob bin mohamed", 1): "Yaacob Bin Mohamed",
    ("ya'acob bin mohamed", 2): "Yaacob Bin Mohamed",
    ("ya'acob bin mohamed", 3): "Yaacob Bin Mohamed",
    ("ya'acob bin mohamed", 4): "Yaacob Bin Mohamed",
    # NOTE: the prefix lookup drops these as ambiguous, because both name forms yield the same key.
    ("mohd ariff", 1): "Mohd Ariff Bin Suradi, Haji",
    ("mohd ariff", 2): "Mohd Ariff Bin Suradi, Haji",
    ("yaacob", 1): "Yaacob Bin Mohamed",
    ("s rajaratnam", 1): "Rajaratnam, S",
    ("s rajaratnam", 2): "Rajaratnam, S",
    ("s rajaratnam", 3): "Rajaratnam, S",
    ("s rajaratnam", 4): "Rajaratnam, S",
    ("s rajaratnam", 5): "Rajaratnam, S",
    ("s rajaratnam", 6): "Rajaratnam, S",
    # Found in the October 2026 attribution pass
    ("mohd ariff", 3): "Mohd Ariff Bin Suradi, Haji",
    ("gerald ee", 9): "Ee, Gerard",
    ("yaacob bin yaacob", 1): "Yaacob Bin Mohamed",
    ("ya'acob", 2): "Yaacob Bin Mohamed",
    ("kenneth chen khoon lap", 9): "Chen Koon Lap, Kenneth",
    ("r sinnakarupan", 9): "Sinnakaruppan, R",
}


_HONORIFIC_SUFFIX_RE = re.compile(r"(?:,\s*[A-Z][A-Z.]*(?:\s+[A-Z][A-Z.]*)*)+$")

_ISLAMIC_SUFFIX_RE = re.compile(r"\s+[Aa]l-[Hh]aj[jh]?\s*$")

_OFFICIAL_ROLE_SUFFIX_RE = re.compile(
    r",\s*(?:Acting\s+)?(?:Financial|Chief|Colonial)\s+Secretary"
    r"|,\s*Attorney[-\s]General"
    r"|,\s*(?:Acting\s+)?Governor\b",
    re.I,
)

_MIN_SURNAME_LOOKUP_LENGTH = 2
_MIN_PREFIX_WORD_COUNT = 2
_MIN_MULTIWORD_SURNAME_LENGTH = 2
_MIN_REARRANGEABLE_WORD_COUNT = 3
_MIN_WORDSET_SUBSET_WORDS = 3

_LEAVE_NOTE_PREFIX = "For information on permission given to Members for leave of absence"

_SECTION_END_RE = re.compile(r"#|\||\*\*|\*[^\s*]|\d{1,2}(?:st|nd|rd|th) [A-Za-z]+,? \d{4}$|(?:Mr|Mdm) Speaker, preceded by")
_MARKUP_RE = re.compile(r"[*|#_\[\]]")
_SPEAKER_OFFICE_NAME = "speaker"

# NOTE: the source lost the start of this entry; the line is the sitting of 10 June 1963.
_TRUNCATED_LINE_TO_ENTRY_LINE: dict[str, str] = {
    "Tunah), Parliamentary Secretary to the Prime Minister.": "Inche Yaacob Bin Mohamed (Bukit Timah), Parliamentary Secretary to the Prime Minister.",
}


def _normalize_for_lookup(name: str) -> str:
    normalized = normalize_name(name)
    # NOTE: only this lookup key loses the lone-initial period, so "S. Rajaratnam" finds "Rajaratnam, S"; stored names keep it.
    normalized = re.sub(r"^([A-Z])\. (?=[A-Z])", r"\1 ", normalized)
    return normalized.lower()


def _get_wordset_key(name: str) -> tuple[frozenset, int]:
    words = period_normalize(name).split()
    return frozenset(words), len(words)


def infer_parliament(parlement_no: Optional[int], volume_no: Optional[int]) -> Optional[int]:
    if parlement_no is not None:
        return parlement_no
    return VOLUME_TO_PARLIAMENT.get(volume_no)  # type: ignore[arg-type]


@dataclass
class SpeakerLookups:
    inverted: dict[tuple[str, int], str]
    direct: dict[tuple[str, int], str]
    bin_free: dict[tuple[str, int], str]
    wordset: dict[tuple[frozenset, int, int], str]
    wordset_subset: dict[tuple[frozenset, int], str]
    prefix: dict[tuple[str, int], str]
    surname_fallback: dict[tuple[str, int], str]


def _build_direct_lookup(speakers: list[Speaker]) -> dict[tuple[str, int], str]:
    counts: dict[tuple[str, int], int] = {}
    entries: list[tuple[tuple[str, int], str]] = []
    for speaker in speakers:
        key = (period_normalize(speaker.name), speaker.parliament_number)
        counts[key] = counts.get(key, 0) + 1
        entries.append((key, speaker.name))
    return {key: canonical for key, canonical in entries if counts[key] == 1}


def _build_bin_free_lookup(
    speakers: list[Speaker],
    direct: dict[tuple[str, int], str],
) -> dict[tuple[str, int], str]:
    counts: dict[tuple[str, int], int] = {}
    entries: list[tuple[tuple[str, int], str]] = []
    for speaker in speakers:
        key = (period_normalize(strip_bin(speaker.name)), speaker.parliament_number)
        counts[key] = counts.get(key, 0) + 1
        entries.append((key, speaker.name))
    return {key: canonical for key, canonical in entries if counts[key] == 1 and key not in direct}


def _build_inverted_lookup(speakers: list[Speaker]) -> dict[tuple[str, int], str]:
    inverted: dict[tuple[str, int], str] = {}
    surname_only_counts: dict[tuple[str, int], int] = {}
    surname_only_entries: list[tuple[tuple[str, int], str]] = []
    for speaker in speakers:
        parliament = speaker.parliament_number
        if ", " in speaker.name:
            natural_stripped = invert_to_natural(speaker.name)
            key = (_normalize_for_lookup(natural_stripped), parliament)
            inverted[key] = speaker.name
            surname = speaker.name.split(", ")[0]
            surname_words = surname.split()
            if len(surname_words) >= _MIN_MULTIWORD_SURNAME_LENGTH:
                surname_key = (_normalize_for_lookup(surname), parliament)
                surname_only_counts[surname_key] = surname_only_counts.get(surname_key, 0) + 1
                surname_only_entries.append((surname_key, speaker.name))
        else:
            words = speaker.name.split()
            if len(words) >= _MIN_REARRANGEABLE_WORD_COUNT:
                rearranged = f"{words[-1]} {' '.join(words[1:-1])} {words[0]}"
                if rearranged != speaker.name:
                    rearranged_stripped = strip_title(rearranged).strip()
                    rearranged_key = (_normalize_for_lookup(rearranged_stripped), parliament)
                    if rearranged_key not in inverted:
                        inverted[rearranged_key] = speaker.name
    for surname_key, canonical in surname_only_entries:
        if surname_only_counts.get(surname_key, 0) == 1 and surname_key not in inverted:
            inverted[surname_key] = canonical
    return inverted


def _build_wordset_lookup(speakers: list[Speaker]) -> dict[tuple[frozenset, int, int], str]:
    triples: list[tuple[str, str, int]] = []
    for speaker in speakers:
        natural = invert_to_natural(speaker.name)
        if natural:
            triples.append((natural, speaker.name, speaker.parliament_number))
        triples.append((speaker.name, speaker.name, speaker.parliament_number))
    counts: dict[tuple[frozenset, int, int], int] = {}
    entries: list[tuple[tuple[frozenset, int, int], str]] = []
    for display, canonical_name, parliament in triples:
        words = period_normalize(display).split()
        key = (frozenset(words), len(words), parliament)
        counts[key] = counts.get(key, 0) + 1
        entries.append((key, canonical_name))
    wordset: dict[tuple[frozenset, int, int], str] = {}
    for key, canonical_name in entries:
        if counts[key] == 1 and key not in wordset:
            wordset[key] = canonical_name
    return wordset


def _build_wordset_subset_lookup(speakers: list[Speaker]) -> dict[tuple[frozenset, int], str]:
    triples: list[tuple[str, str, int]] = []
    for speaker in speakers:
        natural = invert_to_natural(speaker.name)
        if natural:
            triples.append((natural, speaker.name, speaker.parliament_number))
        triples.append((speaker.name, speaker.name, speaker.parliament_number))
    counts: dict[tuple[frozenset, int], int] = {}
    entries: list[tuple[tuple[frozenset, int], str]] = []
    for display, canonical_name, parliament in triples:
        words = period_normalize(strip_title(display)).split()
        if len(words) < _MIN_WORDSET_SUBSET_WORDS:
            continue
        words = [word for word in words if len(word) > 1]
        key = (frozenset(words), parliament)
        counts[key] = counts.get(key, 0) + 1
        entries.append((key, canonical_name))
    wordset_subset: dict[tuple[frozenset, int], str] = {}
    for key, canonical_name in entries:
        if counts[key] == 1 and key not in wordset_subset:
            wordset_subset[key] = canonical_name
    return wordset_subset


def _build_prefix_lookup(speakers: list[Speaker]) -> dict[tuple[str, int], str]:
    forms: list[tuple[str, str, int]] = []
    for speaker in speakers:
        natural = invert_to_natural(speaker.name)
        if natural:
            forms.append((natural, speaker.name, speaker.parliament_number))
        forms.append((speaker.name, speaker.name, speaker.parliament_number))
    prefix_counts: dict[tuple[str, int], int] = {}
    prefix_entries: list[tuple[tuple[str, int], str]] = []
    for display, canonical, parliament in forms:
        words = period_normalize(display).split()
        for prefix_length in range(_MIN_PREFIX_WORD_COUNT, len(words)):
            joined_prefix = " ".join(words[:prefix_length])
            prefix_key = (joined_prefix, parliament)
            prefix_counts[prefix_key] = prefix_counts.get(prefix_key, 0) + 1
            prefix_entries.append((prefix_key, canonical))
    prefix: dict[tuple[str, int], str] = {}
    for prefix_key, canonical in prefix_entries:
        if prefix_counts[prefix_key] == 1 and prefix_key not in prefix:
            prefix[prefix_key] = canonical
    return prefix


def _build_surname_fallback_lookup(speakers: list[Speaker]) -> dict[tuple[str, int], str]:
    surname_counts: dict[tuple[str, int], int] = {}
    surname_entries: list[tuple[tuple[str, int], str]] = []
    for speaker in speakers:
        natural = invert_to_natural(speaker.name) or speaker.name
        words = period_normalize(natural).split()
        if not words:
            continue
        last_word = words[-1]
        if len(last_word) < _MIN_SURNAME_LOOKUP_LENGTH:
            continue
        surname_key = (last_word, speaker.parliament_number)
        surname_counts[surname_key] = surname_counts.get(surname_key, 0) + 1
        surname_entries.append((surname_key, speaker.name))
    return {key: canonical for key, canonical in surname_entries if surname_counts[key] == 1}


def build_speaker_lookups(speakers: list[Speaker]) -> SpeakerLookups:
    direct = _build_direct_lookup(speakers)
    return SpeakerLookups(
        direct=direct,
        bin_free=_build_bin_free_lookup(speakers, direct),
        inverted=_build_inverted_lookup(speakers),
        wordset=_build_wordset_lookup(speakers),
        wordset_subset=_build_wordset_subset_lookup(speakers),
        prefix=_build_prefix_lookup(speakers),
        surname_fallback=_build_surname_fallback_lookup(speakers),
    )


@dataclass(frozen=True)
class ParsedAttendee:
    name: str
    constituency: Optional[str]


def _get_closing_parenthesis_index(text: str, open_index: int) -> Optional[int]:
    depth = 0
    for char_index in range(open_index, len(text)):
        if text[char_index] == "(":
            depth += 1
        elif text[char_index] == ")":
            depth -= 1
            if depth == 0:
                return char_index
    return None


def _strip_name_decorations(name_part: str) -> str:
    # NOTE: the role suffix goes first, so a mixed-case role title never blocks the all-caps honorific strip.
    name = strip_title(name_part.strip())
    name = _OFFICIAL_ROLE_SUFFIX_RE.sub("", name).rstrip(", ").strip()
    name = _HONORIFIC_SUFFIX_RE.sub("", name).rstrip(", ").strip()
    return _ISLAMIC_SUFFIX_RE.sub("", name).strip()


def _parse_name_and_location(text: str) -> ParsedAttendee:
    text = text.strip().rstrip(". ")

    # NOTE: the first parenthetical is the constituency, so a later portfolio parenthetical never replaces it.
    first_open = text.find("(")
    if first_open == -1:
        return ParsedAttendee(_strip_name_decorations(text), None)
    close_index = _get_closing_parenthesis_index(text, first_open)
    if close_index is None:
        return ParsedAttendee(_strip_name_decorations(text[:first_open].rstrip(", )")), None)
    constituency = text[first_open + 1 : close_index].strip()
    return ParsedAttendee(_strip_name_decorations(text[:first_open].rstrip(", ")), constituency)


def _parse_speaker_line(line: str) -> ParsedAttendee:
    line = line.rstrip(". ")
    match = re.search(r"\((.+)\)\s*$", line)
    if match is None:
        return ParsedAttendee("SPEAKER", None)
    inner = match.group(1).strip()
    name_before_constituency = line[: match.start()].partition("SPEAKER")[2].strip()
    if name_before_constituency:
        return ParsedAttendee(_strip_name_decorations(name_before_constituency), inner)
    inner_stripped = strip_title(inner)
    return _parse_name_and_location(inner_stripped)


def _get_presiding_officer_name(sitting_date: str) -> Optional[str]:
    day = parse_sitting_date(sitting_date).date()
    names = [name for first, last, name in SPEAKER_TERMS if first <= day <= last]
    return names[0] if len(names) == 1 else None


def _parse_entry_line(line: str, sitting_date: str) -> Optional[ParsedAttendee]:
    line = line.strip()
    line = _TRUNCATED_LINE_TO_ENTRY_LINE.get(line, line)
    if not line:
        return None
    if line.startswith("* "):
        line = line[2:].strip()
    if not line:
        return None
    if line.startswith("**"):
        line = line[2:].strip()
    line = re.sub(r"^(?:Absent|Present):\s*", "", line, flags=re.IGNORECASE)
    if not line:
        return None
    line = re.sub(r"^\d+(?=[A-Z])", "", line)

    # NOTE: a name entry carries a title or a bracketed constituency; office fragments and prose have neither.
    if strip_title(line) == line and "(" not in line:
        return None

    parsed = _parse_speaker_line(line) if "SPEAKER" in line else _parse_name_and_location(strip_title(line))
    if _MARKUP_RE.search(parsed.name):
        return None
    if parsed.name.lower() != _SPEAKER_OFFICE_NAME:
        return parsed

    # NOTE: a bare "Speaker" entry names the office; the dated table of Speakers names the person.
    presiding_officer_name = _get_presiding_officer_name(sitting_date)
    if presiding_officer_name is None:
        return parsed
    return ParsedAttendee(presiding_officer_name, None)


def _extract_section_lines(content: str, section: str) -> list[str]:
    lines = content.split("\n")
    is_in_section = False
    other_section = "ABSENT" if section == "PRESENT" else "PRESENT"
    entry_lines = []

    for line in lines:
        stripped = line.strip()

        if not is_in_section:
            if re.match(rf"^(?:\*{{2}}|#+)?\s*{section}\s*:(?:\*{{2}})?\s*$", stripped, re.IGNORECASE):
                is_in_section = True
            continue

        if re.match(rf"^(?:\*{{2}}|#+)?\s*{other_section}\s*:(?:\*{{2}})?\s*$", stripped, re.IGNORECASE):
            break
        if _SECTION_END_RE.match(stripped) or stripped == "* * *":
            break
        if re.match(r"^\d+\\\.?\s", stripped):
            break

        if stripped:
            entry_lines.append(line)
            # NOTE: a heading glued to the end of an entry line starts the text that follows the list.
            if "**" in stripped:
                break

    return entry_lines


def _try_name_variant(
    name: str,
    parliament: int,
    lookups: SpeakerLookups,
    is_using_wordset: bool = True,
) -> Optional[str]:
    normalized = period_normalize(name)
    bin_normalized = period_normalize(strip_bin(name))
    canonical = (
        lookups.direct.get((normalized, parliament))
        or lookups.bin_free.get((bin_normalized, parliament))
        or lookups.direct.get((bin_normalized, parliament))
    )
    if canonical:
        return canonical
    if is_using_wordset:
        wordset_canonical = lookups.wordset.get((*_get_wordset_key(name), parliament))
        if wordset_canonical:
            return wordset_canonical
        subset_words = [word for word in period_normalize(name).split() if len(word) > 1]
        subset_canonical = lookups.wordset_subset.get((frozenset(subset_words), parliament))
        if subset_canonical:
            return subset_canonical
    return lookups.prefix.get((normalized, parliament))


def resolve_canonical_name(name: str, parliament: int, lookups: SpeakerLookups) -> Optional[str]:
    name = _OCR_FORM_TO_CORRECTED_NAME.get(period_normalize(name), name)
    canonical = _NAME_PARLIAMENT_TO_CANONICAL_SPEAKER.get((period_normalize(name), parliament))
    if canonical:
        return canonical
    canonical = lookups.inverted.get((_normalize_for_lookup(name), parliament))
    if canonical:
        return canonical
    canonical = _try_name_variant(name, parliament, lookups)
    if canonical:
        return canonical

    spelling_normalised_name = spelling_normalize(name)
    if spelling_normalised_name != name:
        canonical = _try_name_variant(spelling_normalised_name, parliament, lookups)
        if canonical:
            return canonical

    name_without_haji = strip_middle_haji(name)
    if name_without_haji != name:
        canonical = _try_name_variant(name_without_haji, parliament, lookups, is_using_wordset=False)
        if canonical:
            return canonical

    camel_split_name = re.sub(r"([a-z\.])([A-Z])", r"\1 \2", name)
    if camel_split_name != name:
        camel_split_stripped_name = strip_title(camel_split_name).strip()
        canonical = (
            _NAME_PARLIAMENT_TO_CANONICAL_SPEAKER.get((period_normalize(camel_split_stripped_name), parliament))
            or _try_name_variant(camel_split_stripped_name, parliament, lookups)
        )
        if canonical:
            return canonical

    normalised_words = period_normalize(name).split()
    if len(normalised_words) == 1:
        return lookups.surname_fallback.get((normalised_words[0], parliament))
    return None


@dataclass(frozen=True)
class ConstituencyLookups:
    printed_parliament_to_constituency: dict[tuple[str, Optional[int]], str]
    printed_to_constituency: dict[str, str]
    sitting_speaker_printed_to_constituency: dict[tuple[Optional[str], Optional[str], str], str]


@dataclass(frozen=True)
class AttendanceNameChange:
    id: int
    sitting_id: int
    speaker_name_before: Optional[str]
    speaker_name_after: Optional[str]
    is_present: Optional[bool]
    location_name: Optional[str]
    speaker_id: Optional[int]


@dataclass(frozen=True)
class LocationChange:
    id: int
    speaker_name: Optional[str]
    sitting_date: Optional[str]
    location_name_before: str
    location_name_after: str


def build_constituency_lookups(constituency_names: ConstituencyNames) -> ConstituencyLookups:
    return ConstituencyLookups(
        printed_parliament_to_constituency={
            (name.printed, name.parliament_number): name.constituency
            for name in constituency_names.names
            if name.parliament_number is not None
        },
        printed_to_constituency={name.printed: name.constituency for name in constituency_names.names if name.parliament_number is None},
        sitting_speaker_printed_to_constituency={
            (row.sitting_date, row.speaker_name, row.printed): row.constituency for row in constituency_names.rows
        },
    )


def get_constituency_name(
    printed: Optional[str],
    parliament: Optional[int],
    sitting_date: Optional[str],
    speaker_name: Optional[str],
    lookups: ConstituencyLookups,
) -> Optional[str]:
    if printed is None:
        return None
    row_constituency = lookups.sitting_speaker_printed_to_constituency.get((sitting_date, speaker_name, printed))
    if row_constituency is not None:
        return row_constituency
    parliament_constituency = lookups.printed_parliament_to_constituency.get((printed, parliament))
    if parliament_constituency is not None:
        return parliament_constituency
    return lookups.printed_to_constituency.get(printed, printed)


def get_location_changes(rows: list[AttendanceLocationRow], lookups: ConstituencyLookups) -> list[LocationChange]:
    location_changes = []
    for row in rows:
        location_name_after = get_constituency_name(
            row.location_name, infer_parliament(row.parlement_no, row.volume_no), row.sitting_date, row.speaker_name, lookups
        )
        if location_name_after == row.location_name:
            continue
        location_changes.append(LocationChange(row.id, row.speaker_name, row.sitting_date, row.location_name, location_name_after))
    return location_changes


def _drop_repeated_attendees(records: list[Attendance]) -> list[Attendance]:
    speaker_name_to_record: dict[Optional[str], Attendance] = {}
    for record in records:
        kept_record = speaker_name_to_record.get(record.speaker_name)
        if kept_record is None or (record.is_present and not kept_record.is_present):
            speaker_name_to_record[record.speaker_name] = record
    return list(speaker_name_to_record.values())


def get_sitting_attendance(sitting: Sitting, lookups: SpeakerLookups, constituency_lookups: ConstituencyLookups) -> list[Attendance]:
    if not sitting.markdown_content:
        return []

    parliament = infer_parliament(sitting.parlement_no, sitting.volume_no)
    content = sitting.markdown_content
    records = []

    for section, is_present in [("PRESENT", True), ("ABSENT", False)]:
        for line in _extract_section_lines(content, section):
            parsed = _parse_entry_line(line, sitting.sitting_date)
            if parsed is None:
                continue
            if not parsed.name:
                continue
            name = normalize_name(parsed.name)
            canonical = None if parliament is None else resolve_canonical_name(name, parliament, lookups)
            speaker_name = canonical or name
            records.append(Attendance(
                sitting_id=sitting.id,
                speaker_name=speaker_name,
                is_present=is_present,
                location_name=get_constituency_name(parsed.constituency, parliament, sitting.sitting_date, speaker_name, constituency_lookups),
            ))

    return _drop_repeated_attendees(records)


def get_sitting_attendance_from_list(sitting: Sitting, lookups: SpeakerLookups, constituency_lookups: ConstituencyLookups) -> list[Attendance]:
    if sitting.attendance_list is None:
        return []

    parliament = infer_parliament(sitting.parlement_no, sitting.volume_no)
    records = []

    for raw_entry in json.loads(sitting.attendance_list):
        entry = HansardReportAttendanceEntry.model_validate(raw_entry)
        if entry.mp_name is None:
            continue
        if entry.mp_name.startswith(_LEAVE_NOTE_PREFIX):
            continue
        parsed = _parse_entry_line(entry.mp_name, sitting.sitting_date)
        if parsed is None:
            continue
        if not parsed.name:
            continue
        name = normalize_name(parsed.name)
        canonical = None if parliament is None else resolve_canonical_name(name, parliament, lookups)
        speaker_name = canonical or name
        records.append(Attendance(
            sitting_id=sitting.id,
            speaker_name=speaker_name,
            is_present=entry.attendance,
            location_name=get_constituency_name(parsed.constituency, parliament, sitting.sitting_date, speaker_name, constituency_lookups),
        ))

    return _drop_repeated_attendees(records)


def build_sitting_attendances(sitting: Sitting, lookups: SpeakerLookups, constituency_lookups: ConstituencyLookups) -> list[Attendance]:
    if sitting.markdown_content is not None:
        return get_sitting_attendance(sitting, lookups, constituency_lookups)
    return get_sitting_attendance_from_list(sitting, lookups, constituency_lookups)


def get_attendance_name_changes(sitting_id: int, stored_rows: list[Attendance], built_rows: list[Attendance]) -> list[AttendanceNameChange]:
    if len(stored_rows) != len(built_rows):
        raise HansardWriteCheckError(f"Sitting {sitting_id}: {len(stored_rows)} stored attendance rows, stage 7 builds {len(built_rows)}")
    name_changes = []
    for stored_row, built_row in zip(stored_rows, built_rows):
        if stored_row.is_present != built_row.is_present:
            raise HansardWriteCheckError(f"Attendance row {stored_row.id}: presence {stored_row.is_present}, stage 7 builds {built_row.is_present}")
        if stored_row.location_name != built_row.location_name:
            raise HansardWriteCheckError(f"Attendance row {stored_row.id}: location {stored_row.location_name!r}, stage 7 builds {built_row.location_name!r}")
        if stored_row.speaker_name == built_row.speaker_name:
            continue
        name_changes.append(AttendanceNameChange(
            stored_row.id, sitting_id, stored_row.speaker_name, built_row.speaker_name,
            stored_row.is_present, stored_row.location_name, stored_row.speaker_id,
        ))
    return name_changes
