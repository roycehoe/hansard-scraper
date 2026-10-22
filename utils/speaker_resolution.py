import re
from dataclasses import dataclass
from typing import Optional

from utils.names import (
    normalize_name,
    period_normalize,
    spelling_normalize,
    strip_bin,
    strip_middle_haji,
    strip_title,
)

# NOTE: scanner errors made in every parliament go here; fixes that need a parliament go in NAME_PARLIAMENT_TO_CANONICAL_SPEAKER.
_OCR_FORM_TO_CORRECTED_NAME: dict[str, str] = {
    "lai tha chai": "Lai Tai Chai",  # vols 32-51, parl 3-6
    "lai tha chia": "Lai Tai Chai",
    "chin ham tong": "Chin Harn Tong",
    "lbrahim othman": "Ibrahim Othman",
    "sha'ari bib tadin": "Sha'ari Bin Tadin",
    "tan soc khoon": "Tan Soo Khoon",
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
NAME_PARLIAMENT_TO_CANONICAL_SPEAKER: dict[tuple[str, int], str] = {
    ("d s marshall", 0): "David Marshall",
    # Mrs Devan Nair, not C. V. Devan Nair
    ("c v devan nair", 1): "Devan Nair, Mrs",
    ("william goode, k c m g", 0): "William Goode",
    ("g e n oehlers", 0): "George Oehlers",
    ("rahamat bin kenap", 1): "Rahmat Bin Kenap",
    ("rahamat", 1): "Rahmat Bin Kenap",
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
    ("masagos zulkifli b m m", 15): "Masagos Zulkifli Bin Masagos Mohamad",
    ("kenneth tiong boon kiat", 15): "Kenneth Tiong",
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
    ("mohd ariff", 3): "Mohd Ariff Bin Suradi, Haji",
    ("gerald ee", 9): "Ee, Gerard",
    ("yaacob bin yaacob", 1): "Yaacob Bin Mohamed",
    ("ya'acob", 2): "Yaacob Bin Mohamed",
    ("kenneth chen khoon lap", 9): "Chen Koon Lap, Kenneth",
    ("r sinnakarupan", 9): "Sinnakaruppan, R",
}


def normalize_for_lookup(name: str) -> str:
    normalized = normalize_name(name)
    # NOTE: only this lookup key loses the lone-initial period, so "S. Rajaratnam" finds "Rajaratnam, S"; stored names keep it.
    normalized = re.sub(r"^([A-Z])\. (?=[A-Z])", r"\1 ", normalized)
    return normalized.lower()


@dataclass(frozen=True)
class SpeakerLookups:
    inverted: dict[tuple[str, int], str]
    direct: dict[tuple[str, int], str]
    bin_free: dict[tuple[str, int], str]
    wordset: dict[tuple[frozenset, int, int], str]
    wordset_subset: dict[tuple[frozenset, int], str]
    prefix: dict[tuple[str, int], str]
    surname_fallback: dict[tuple[str, int], str]


def _get_variant_canonical_name(
    name: str,
    parliament_number: int,
    lookups: SpeakerLookups,
    is_using_wordset: bool = True,
) -> Optional[str]:
    normalized = period_normalize(name)
    bin_normalized = period_normalize(strip_bin(name))
    canonical_name = (
        lookups.direct.get((normalized, parliament_number))
        or lookups.bin_free.get((bin_normalized, parliament_number))
        or lookups.direct.get((bin_normalized, parliament_number))
    )
    if canonical_name:
        return canonical_name
    if is_using_wordset:
        words = normalized.split()
        wordset_canonical_name = lookups.wordset.get((frozenset(words), len(words), parliament_number))
        if wordset_canonical_name:
            return wordset_canonical_name
        subset_words = [word for word in period_normalize(name).split() if len(word) > 1]
        subset_canonical_name = lookups.wordset_subset.get((frozenset(subset_words), parliament_number))
        if subset_canonical_name:
            return subset_canonical_name
    return lookups.prefix.get((normalized, parliament_number))


def resolve_canonical_name(name: str, parliament_number: int, lookups: SpeakerLookups) -> Optional[str]:
    name = _OCR_FORM_TO_CORRECTED_NAME.get(period_normalize(name), name)
    canonical_name = NAME_PARLIAMENT_TO_CANONICAL_SPEAKER.get((period_normalize(name), parliament_number))
    if canonical_name:
        return canonical_name
    canonical_name = lookups.inverted.get((normalize_for_lookup(name), parliament_number))
    if canonical_name:
        return canonical_name
    canonical_name = _get_variant_canonical_name(name, parliament_number, lookups)
    if canonical_name:
        return canonical_name

    spelling_normalized_name = spelling_normalize(name)
    if spelling_normalized_name != name:
        canonical_name = _get_variant_canonical_name(spelling_normalized_name, parliament_number, lookups)
        if canonical_name:
            return canonical_name

    name_without_haji = strip_middle_haji(name)
    if name_without_haji != name:
        canonical_name = _get_variant_canonical_name(name_without_haji, parliament_number, lookups, is_using_wordset=False)
        if canonical_name:
            return canonical_name

    camel_split_name = re.sub(r"([a-z\.])([A-Z])", r"\1 \2", name)
    if camel_split_name != name:
        camel_split_stripped_name = strip_title(camel_split_name).strip()
        canonical_name = (
            NAME_PARLIAMENT_TO_CANONICAL_SPEAKER.get((period_normalize(camel_split_stripped_name), parliament_number))
            or _get_variant_canonical_name(camel_split_stripped_name, parliament_number, lookups)
        )
        if canonical_name:
            return canonical_name

    normalized_words = period_normalize(name).split()
    if len(normalized_words) == 1:
        return lookups.surname_fallback.get((normalized_words[0], parliament_number))
    return None
