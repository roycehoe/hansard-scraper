import re
from dataclasses import dataclass
from typing import Optional

from database.attendance import Attendance
from database.sitting import Sitting
from database.speaker import Speaker

# Derived from markdown content: "Parliament No:| N" header in every sitting.
VOLUME_TO_PARLIAMENT: dict[int, int] = {
    1: 1, 2: 1, 3: 1, 4: 1, 6: 1, 7: 1, 8: 1, 9: 1, 11: 1,
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

# Parliament-agnostic OCR corrections applied before the cascade.
# Key: _period_normalize(ocr_form) → corrected name fed into the cascade.
# Use this for character-substitution errors and post-nominal decorations — errors that
# the same OCR scanner makes regardless of which parliament the sitting belongs to.
# For genuinely parliament-specific fixes (surname disambiguation, inverted canonicals)
# use _NAME_PARLIAMENT_TO_CANONICAL_SPEAKER below.
_OCR_FORM_TO_CORRECTED_NAME: dict[str, str] = {
    # Character-substitution errors
    "lai tha chai": "Lai Tai Chai",       # Tha→Tai (vols 32-51, parl=3-6)
    "lai tha chia": "Lai Tai Chai",
    "chin ham tong": "Chin Harn Tong",    # Ham→Harn
    "lbrahim othman": "Ibrahim Othman",   # l→I (lowercase for capital)
    "yong nyuk lm": "Yong Nyuk Lin",      # Lm→Lin (truncated)
    "leong keng sung": "Leong Keng Seng", # u→e
    "gob keng swee": "Goh Keng Swee",     # b→h
    "gob chew chua": "Goh Chew Chua",
    "a rahim lshak": "A. Rahim Ishak",    # l→I in "Ishak"
    "jek youn thong": "Jek Yeun Thong",   # ou→eu
    "jek yuen thong": "Jek Yeun Thong",   # ue→eu
    "wee loon boon": "Wee Toon Boon",     # l→T (lowercase for uppercase)
    "wee toon. boon": "Wee Toon Boon",    # spurious period after "Toon"
    "yaacoh bin mohamed": "Yaacob Bin Mohamed",  # h→b
    "toh chih chye": "Toh Chin Chye",     # h→n
    "ng kah tins": "Ng Kah Ting",         # s→g (spurious suffix)
    "ho chong choon": "Ho Cheng Choon",   # o→e
    "ho kah loong": "Ho Kah Leong",       # oo→eo
    "lob miaw gong": "Loh Miaw Gong",     # b→h
    "sia kat hui": "Sia Kah Hui",         # t→h
    "buang bin omar junied": "Buang Bin Omar Junid",  # spurious 'e'
    "wang soon fong": "Wong Soon Fong",   # a→o
    "urn cheng lock": "Lim Cheng Lock",   # Urn→Lim
    "sahorah binte ahmad": "Sahorah Binte Ahmat",  # d→t
    "he puay choc.": "Hoe Puay Choo",    # He→Hoe, Choc→Choo
    "scow peck leng": "Seow Peck Leng",  # c→e
    "tan kb gan": "Tan Kia Gan",          # Kb→Kia
    "ahmed bin ibrahim": "Ahmad Bin Ibrahim",  # e→a
    "sob ghee soon": "Soh Ghee Soon",    # b→h
    "low for tuck": "Low Por Tuck",      # F→P
    "lim yew yock": "Lim Yew Hock",     # Y→H
    # Rahmat Bin Kenap: suffix/prefix OCR corruption
    "rahmat bin kenap a1-haj": "Rahmat Bin Kenap",  # A1→Al (digit 1 for l)
    "haii rahmat bin kenap": "Rahmat Bin Kenap",    # Haii prefix = OCR of "Haji"
    "rahmat bin kensp": "Rahmat Bin Kenap",          # Kensp→Kenap
    # S. Rajaratnam OCR variants → corrected form hits the ("s rajaratnam", p) override
    "s rajaratnarn": "S. Rajaratnam",
    "s rajaratam": "S. Rajaratnam",
    "s raiaratnam": "S. Rajaratnam",
    # Yaacob Bin Mohamed with Islamic suffix appended (speech transcripts, parl=0 sittings)
    "yaacob bin mohamed al-haj": "Yaacob Bin Mohamed",
    # OCR-corrupted prefix not caught by strip_title (period after lowercase letter)
    "inche. ahmad jabri bin mohammad akib": "Ahmad Jabri Bin Mohammad Akib",
    # Post-nominal decorations: _period_normalize expands uppercase initials (D.U.T.→d u t)
    # and preserves trailing periods after lowercase letters (San.→san.)
    "lim kim san. d u t": "Lim Kim San",
    "ho see beng. b b m": "Ho See Beng",
    "lim yew hock. s m n": "Lim Yew Hock",
    "thio chan bee. j p": "Thio Chan Bee",
    "thio chan bee, .j p": "Thio Chan Bee",
    "thio chan bee, j p": "Thio Chan Bee",
    "thio chan bee, j.p.": "Thio Chan Bee",  # lowercase j.p. survives as-is
    "r jumabhoy. c b e": "Jumabhoy, R.",
    "abdul hamid bin haji jumat. p m n": "Abdul Hamid Bin Haji Jumat",
    "ong piah teng. o b e": "Ong Piah Teng",
    "tan eng liang. b b m": "Tan Eng Liang",  # B.B.M. post-nominal
    # Character-substitution errors — parl=3–5 era names
    "yeo choc kok": "Yeo Choo Kok",      # c→o
    "yoo choo kok": "Yeo Choo Kok",      # oo→eo in first syllable
    "chai chong vii": "Chai Chong Yii",  # V→Y
    "ivan batist": "Ivan Baptist",        # truncated 'Baptist'
    "lee yiok song": "Lee Yiok Seng",    # o→e
    "lee chiaw memg": "Lee Chiaw Meng",  # g→ng (truncated)
    "mg nam piau": "Ang Nam Piau",       # Mg→Ang
    # parl=4–6 era OCR variants
    "lou teik soon": "Lau Teik Soon",    # o→a (vol 39, parl=4)
    "eugune yap giau cheng": "Eugene Yap Giau Cheng",  # u→e; cascade → inverted "Yap Giau Cheng, Eugene"
    "yeo n ing hong": "Yeo Ning Hong",   # space-split 'Ning' (vol 45, parl=6)
    # Mixed-era OCR variants
    "koh kam son": "Koh Lam Son",        # m→l (vol 50, parl=6)
    "rohan'bin kamis": "Rohan Bin Kamis",  # apostrophe for space (vols 38-44, parl=4-5)
    "p govindasamy": "P. Govindaswamy",  # amy→awamy; cascade → inverted "Govindaswamy, P." (parl=1-4)
    "p govindaswarny": "P. Govindaswamy",  # rny→my variant
    "n govindaswamy": "N. Govindasamy",  # extra 'w'; cascade → inverted "Govindasamy, N." (parl=2-4)
    # Post-nominal P.B.m. with lowercase 'm' (parl=5-8)
    "wong kwei cheong, p bm.": "Wong Kwei Cheong",
    "tay eng soon, p bm.": "Tay Eng Soon",
    # Character substitutions — colonial and early parliament era
    "mohd ali bin aiwi": "Mohd Ali Bin Alwi",  # i→l in "Alwi" (parl=1)
    "chiang hal ding": "Chiang Hai Ding",       # l→i (vols 30-32, parl=2-3)
    "yeo loon chia": "Yeo Toon Chia",           # l→T (vols 34-36, parl=3-4)
    "scab mui kok": "Seah Mui Kok",             # c→e, b→h (vols 32-33, parl=3)
    "mg kok peng": "Ang Kok Peng",              # Mg→Ang (vol 33, parl=3)
    "sidek bin sa niff": "Sidek Bin Saniff",    # space inserted in 'Saniff' (vols 42-45, parl=5-6)
    # Space-split 'Ning' at a different position than iter 9
    "yeo ni ng hong": "Yeo Ning Hong",          # 'Ni ng' split (cf. 'N ing' in iter 9)
    # Trailing period on name (no post-nominal)
    "francis thomas.": "Francis Thomas",
    "john mammen.": "John Mammen",
    # Ahmad Jabri prefix OCR variants not caught by existing "inche. ..." entry
    "lnche ahmad jabri bin mohammad akib": "Ahmad Jabri Bin Mohammad Akib",  # l→I in 'Inche'
    "inche, ahmad jabri bin mohammad akib": "Ahmad Jabri Bin Mohammad Akib",  # comma for period
    # Role-appended colonial official names (parl=0/1 era)
    "oon khye kiang. financial secretary": "Oon Khye Kiang",
    "t m hart, c m g financial secretary": "T.M. Hart",  # cascade → inverted "Hart, T.M."
    # Character substitutions — parl=2–6 era
    "sidek bin siniff": "Sidek Bin Saniff",          # i→a (cf. iter 11 'Sa niff' form)
    "yea choo kok": "Yeo Choo Kok",                  # a→e
    "goh ghok tong": "Goh Chok Tong",                # Gh→Ch
    "hwang soo tin": "Hwang Soo Jin",                # t→j
    "othmah bin haron eusofe": "Othman Bin Haron Eusofe",  # h→n
    "s joyakumar": "S Jayakumar",                    # o→a
    "tsy eng soon": "Tay Eng Soon",                  # Ts→Ta
    "lea kuan yew": "Lee Kuan Yew",                  # a→e
    "lau telk soon": "Lau Teik Soon",                # transposed l/k in 'Teik'
    # Post-nominal B.B.m. comma separator variant (cf. "ho see beng. b b m" with period)
    "ho see beng, b bm.": "Ho See Beng",
    # Trailing paren from malformed constituency stripping
    "r jumabhoy)": "Jumabhoy, R.",  # cascade → direct lookup "Jumabhoy, R." at parl=1
    # Post-nominal B.B.M. with period separator on Yeoh Ghim Seng
    "yeoh ghim seng. b b m": "Yeoh Ghim Seng",
    "yeoh ghim seng, b b m, .j p": "Yeoh Ghim Seng",   # B.B.M., .J.P.
    "yeoh ghim seng, b b m,. j p": "Yeoh Ghim Seng",   # B B M,. J.P. variant
    # Character substitutions and space-inserted forms
    "p selvedurai": "P. Selvadurai",     # e→a; cascade → inverted "Selvadurai, P."
    "mold. ariff bin suradi": "Mohd Ariff Bin Suradi, Haji",  # Mold→Mohd
    "ow chin. hock": "Ow Chin Hock",    # spurious period in name (parl=4-9)
    "m k a jabba.r": "M K A Jabbar",    # period inserted in 'Jabbar' (parl=5)
    "mah bow t2an": "Mah Bow Tan",      # '2' spuriously inserted (parl=7-8)
    # Saidi Shariff OCR variants — cascade uses _strip_middle_haji to find "Saidi Shariff"
    "said! haji shariff": "Saidi Haji Shariff",   # ! for 'i'
    "saidi haii shariff": "Saidi Haji Shariff",   # Haii→Haji
    # Role-appended name forms
    "jek yeun thong minister for culture": "Jek Yeun Thong",
    "goh keng swee minister of defence": "Goh Keng Swee",
    "ahmad bin ibrahim (sembawang. minister for labour": "Ahmad Bin Ibrahim",
    "lee kuan yew (tanjong pagan. prime minister": "Lee Kuan Yew",
    # Post-nominal decorated forms for colonial officials
    "george oehlers. o b e": "George Oehlers",
    "george oehlers, (o b e": "George Oehlers",
    "w a c goode. c m g": "W.A.C. Goode",  # cascade → inverted "Goode, W.A.C."
    # Sha'ari Bin Tadin OCR variants
    "sha'ari bin tedin": "Sha'ari Bin Tadin",  # e→a in 'Tadin'
    "sh'ari bin tadin": "Sha'ari Bin Tadin",   # missing 'a' after Sh'
    "s1ia'ari bin tadin": "Sha'ari Bin Tadin",  # digit 1 for 'a' (S1ia→Sha)
    # Comma/punctuation misplacements
    "ahmad, bin ibrahim": "Ahmad Bin Ibrahim",   # comma misplacement
    "j, f conceicao": "J.F. Conceicao",         # J, F → J.F.; cascade → inverted "Conceicao, J.F."
    # Post-nominal variants not yet caught
    "hon sui sen. d u b c": "Hon Sui Sen",       # D.U.B.C. honour
    "chau sik ting, p bm.": "Chau Sik Ting",    # P.B.m.; cascade → inverted "Chau Sik Ting, Dr"
    "ho see beng, a.bm.": "Ho See Beng",        # a.B.m. variant (lowercase 'a')
    # Trailing apostrophe / spurious period in name
    "mohd ghazali bin ismail'": "Mohd Ghazali Bin Ismail",
    "hwang. soo jin": "Hwang Soo Jin",
    "fong. sip chee": "Fong Sip Chee",
    # Inverted-initial variant
    "p seivadurai": "P. Selvadurai",             # ei→el; cascade → inverted "Selvadurai, P."
    # "Should already resolve" anomalies — existing entries cover different name or separator form
    "inche. buang bin omar junid": "Buang Bin Omar Junid",  # existing entries only cover Ahmad Jabri
    "j,f conceicao": "J.F. Conceicao",          # existing "j, f conceicao" has space; this has none
    "ong piah teng, o b e": "Ong Piah Teng",    # existing "ong piah teng. o b e" uses period sep
    "ang nam piau.": "Ang Nam Piau",             # existing "mg nam piau" handles Mg→Ang; trailing period not covered
    "yeoh ghim seng)": "Yeoh Ghim Seng",        # trailing paren (existing entries cover post-nominal forms)
    "p selvadural": "P. Selvadurai",             # ural→urai; cascade → inverted "Selvadurai, P."
    "yaacob bin mohamed ai-haj": "Yaacob Bin Mohamed",  # AI-Haj (uppercase I) vs al-haj (lowercase l)
    # Character substitutions — parl=2–5 era new variants
    "hwang soo un": "Hwang Soo Jin",             # un→Jin (parl=2, vol=27)
    "lau teik sobn": "Lau Teik Soon",            # Sobn→Soon (parl=5, vol=45)
    "mohd mi bin alwi": "Mohd Ali Bin Alwi",     # Mi→Ali (parl=0, vol=20)
    "othman bin haron elisofe": "Othman Bin Haron Eusofe",  # ELisofe→Eusofe (parl=5, vol=45)
    "adbul hamid bin haji jumat": "Abdul Hamid Bin Haji Jumat",  # Adbul→Abdul (parl=1, vol=14)
    "dl chiang hai ding": "Chiang Hai Ding",     # DL=OCR of Dr/Mr (parl=2, vol=32)
    "dr yeoh ghim seng": "Yeoh Ghim Seng",       # DR=all-caps OCR not in _TITLE_PREFIXES (parl=6, vol=50)
    "mr tan soo khoon": "Tan Soo Khoon",         # MR=all-caps OCR not in _TITLE_PREFIXES (parl=6, vol=50)
    "cha,u sik ting": "Chau Sik Ting",           # comma inside name (parl=5, vol=42)
    "lee tee long": "Lee Tee Tong",              # long→Tong (parl=0→1, vol=23)
    "ch'ng lit koon": "Ch'ng Jit Koon",          # lit→Jit (parl=3, vol=32)
    "ong tang cheong": "Ong Teng Cheong",        # Tang→Teng (parl=4, vol=39)
    "ong tong cheong": "Ong Teng Cheong",        # Tong→Teng (parl=5, vol=43)
    "lee yock suen": "Lee Yock Suan",            # Suen→Suan (parl=5, vol=40)
    "sia khoon soong": "Sia Khoon Seong",        # Soong→Seong (parl=4, vol=38)
    "lirn choon mong": "Lim Choon Mong",         # Lirn→Lim (parl=1, vol=9)
    "lim you eng": "Lin You Eng",                # Lim→Lin (parl=1, vol=15)
    "mt. lin you eng": "Lin You Eng",            # Mt.=OCR of Mr.; same person as Lim You Eng (parl=1, vol=14)
    "phue bah lee": "Phua Bah Lee",              # Phue→Phua (parl=5, vol=43)
    "phua bali lee": "Phua Bah Lee",             # Bali→Bah (parl=3, vol=31)
    "c v devan nair": "Devan Nair",              # C.V. prefix not resolvable via wordset (parl=0→1, vol=23)
    # Post-nominal decoration variants not yet covered
    "ang kok peng, b bm.": "Ang Kok Peng",      # B.B.m. (lowercase m survives _period_normalize, parl=5, vol=44)
    "ang kok peng. b b m": "Ang Kok Peng",      # B.B.M. with period separator (parl=3, vol=36)
    "seah mui kok, b bm.": "Seah Mui Kok",      # B.B.m. (parl=5, vol=43)
    "seah mui kok, e.bm.": "Seah Mui Kok",      # e.B.m. (lowercase e+period survives, parl=5, vol=43)
    "seah mui kok, ba.m.": "Seah Mui Kok",      # B.a.m. (B. stripped, a. survives, parl=5, vol=44)
    "thio chan bee, j p tanglin)": "Thio Chan Bee",  # post-nominal J.P. + constituency (parl=1, vol=15)
    # Post-nominal for colonial officials
    "c h butterfield. q c": "C.H. Butterfield",  # Q.C. post-nominal; cascade → inverted "Butterfield, C.H." (parl=1, vol=2)
    "e p shanks, q c attorney-general": "E.P. Shanks",  # Q.C. + role; cascade → inverted "Shanks, E.P." (parl=1, vol=6)
    # Constituency+role appended forms
    "goh keng swee kreta ayer) minister for finance": "Goh Keng Swee",   # (parl=0→1, vol=23)
    "lim kim san cairnhill), minister for national development": "Lim Kim San",  # (parl=0→1, vol=23)
    "chor yeok eng bukit timah), parliamentary secretary to the minister for health": "Chor Yeok Eng",  # (parl=3, vol=31)
    "ngeow pack hua aboon lay)": "Ngeow Pack Hua",   # OCR constituency (parl=4, vol=38)
    "ya'acob bin mohamed kampong ubi), minister of state, prime minister's office": "Yaacob Bin Mohamed",  # (parl=2, vol=27)
    # Trailing punctuation on real names
    "wong foo nam.": "Wong Foo Nam",             # trailing period (parl=1, vol=2)
    "s v lingam.": "S.V. Lingam",               # trailing period; cascade → inverted "Lingam, S.V." (parl=1, vol=11)
    "c h koh.": "C.H. Koh",                     # trailing period; cascade → inverted "Koh, C.H." (parl=1, vol=15)
    "urn kim san": "Lim Kim San",                # Urn→Lim (cf. "urn cheng lock"; parl=2, vol=30)
    # Presiding-officer role suffix in attendance lines
    "punch coomaraswamy, deputy speaker": "P. Coomaraswamy",  # cascade → inverted "Coomaraswamy, P." (parl=1, vol=25)
    "p coomaraswamy, deputy speaker": "P. Coomaraswamy",      # initials-only form (parl=1, vol=25)
    # Markdown/formatting artifacts surviving into existing DB rows (parser fix prevents future occurrences)
    "absent: mr ahmad mohd magad": "Ahmad Mohd Magad",  # Absent: prefix not stripped (parl=9, vol=70)
    "**mr ng kah ting": "Ng Kah Ting",          # markdown bold prefix (parl=2, vol=27)
}

# Manual overrides for names that cannot be resolved by general normalisation rules.
# Key: (period_normalized_extracted_name, parliament_number)
# Value: canonical Speaker.name
# Use for: (a) surname-only forms where parliament is needed for disambiguation,
# (b) inverted-format canonicals the cascade can't reach without explicit mapping.
# Do NOT use for OCR character substitutions — those belong in _OCR_FORM_TO_CORRECTED_NAME above.
_NAME_PARLIAMENT_TO_CANONICAL_SPEAKER: dict[tuple[str, int], str] = {
    # Colonial-era variant spellings
    # "D.S. Marshall" is David Marshall (Labour Front Chief Minister)
    ("d s marshall", 1): "David Marshall",
    # "G.E.N. Oehlers" is George E.N. Oehlers (Labour Front)
    ("g e n oehlers", 1): "George Oehlers",
    # "Rahamat" is a spelling variant of "Rahmat" (already in Speaker table)
    ("rahamat bin kenap", 1): "Rahmat Bin Kenap",
    # OCR spelling variants of existing parliament-1 MPs
    # "Koo Young" is "Koo Yong" (Barisan Sosialis)
    ("koo young", 1): "Koo Yong",
    # "Chew Chin Han" is "Chew Chin Harn" (People's Action Party)
    ("chew chin han", 1): "Chew Chin Harn",
    # Surname-only speech forms for colonial officials -- all unique in parliament 1
    ("hart", 1): "Hart, T.M.",
    ("goode", 1): "Goode, W.A.C.",
    ("butterfield", 1): "Butterfield, C.H.",
    ("shanks", 1): "Shanks, E.P.",
    ("david", 1): "David, E.B.",
    ("sutherland", 1): "Sutherland, G.A.P.",
    ("stewart", 1): "Stewart, S.T.",
    ("davies", 1): "Davies, E.J.",
    ("higham", 1): "Higham, J.D.",
    # Speaker table has typo "Gahni" instead of "Ghani"
    ("ahmad khalis bin abdul ghani", 10): "Ahmad Khalis bin Abdul Gahni",
    # "B M M" is an abbreviation of "Bin Masagos Mohamad"
    ("masagos zulkifli b m m", 11): "Masagos Zulkifli Bin Masagos Mohamad",
    ("masagos zulkifli b m m", 12): "Masagos Zulkifli Bin Masagos Mohamad",
    # Extracted name lacks the ", Dr" title suffix present in Speaker.name
    ("lim chun leng, michael", 8): "Lim Chun Leng, Michael, Dr",
    ("lim chun leng, michael", 9): "Lim Chun Leng, Michael, Dr",
    ("lim chun leng, michael", 10): "Lim Chun Leng, Michael, Dr",
    # One-letter spelling difference in Speaker.name
    ("abdul nasser bin kamaruddin", 7): "Abdul Nasser Bin Kamarudin",
    ("seet ai mee", 7): "Seet Ai Mei, Dr",
    # Surname-only references: "Mr Jeyaretnam", "Prof. Jayakumar", etc.
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
    # Barker, E.W. stored in inverted format; last word of canonical is "E.W." not "Barker"
    ("barker", 1): "Barker, E.W.",
    ("barker", 2): "Barker, E.W.",
    ("barker", 3): "Barker, E.W.",
    ("barker", 4): "Barker, E.W.",
    ("barker", 5): "Barker, E.W.",
    ("barker", 6): "Barker, E.W.",
    # Bani, S.T. stored in inverted format; resolved after parl=0 fallback to parl=1
    ("bani", 1): "Bani, S.T.",
    # Full-name variant: "Joshua Benjamin Jeyaretnam" for J B Jeyaretnam
    ("joshua benjamin jeyaretnam", 5): "J B Jeyaretnam",
    ("joshua benjamin jeyaretnam", 6): "J B Jeyaretnam",
    # Apostrophe variant: "Ya'acob" vs "Yaacob" in Speaker table
    ("ya'acob bin mohamed", 1): "Yaacob Bin Mohamed",
    ("ya'acob bin mohamed", 2): "Yaacob Bin Mohamed",
    ("ya'acob bin mohamed", 3): "Yaacob Bin Mohamed",
    ("ya'acob bin mohamed", 4): "Yaacob Bin Mohamed",
    # Mohd Ariff Bin Suradi — prefix lookup drops ("mohd ariff", N) because both the
    # natural and original forms of the inverted name generate the same prefix key,
    # causing the deduplication count to hit 2 and exclude it as ambiguous.
    ("mohd ariff", 1): "Mohd Ariff Bin Suradi, Haji",
    ("mohd ariff", 2): "Mohd Ariff Bin Suradi, Haji",
    # Tuan Haji Yaacob — strip_title leaves "Yaacob" (single word); no lookup reaches
    # "Yaacob Bin Mohamed" from a bare first name alone.
    ("yaacob", 1): "Yaacob Bin Mohamed",
    # S. Rajaratnam stored inverted as "Rajaratnam, S"; "Mr. S. Rajaratnam" leaves "Mr."
    # after strip_title which doesn't handle the period-after-title form
    ("s rajaratnam", 1): "Rajaratnam, S",
    ("s rajaratnam", 2): "Rajaratnam, S",
    ("s rajaratnam", 3): "Rajaratnam, S",
    ("s rajaratnam", 4): "Rajaratnam, S",
    ("s rajaratnam", 5): "Rajaratnam, S",
    ("s rajaratnam", 6): "Rajaratnam, S",
}


# Title prefixes, longest first to avoid partial matches.
_TITLE_PREFIXES = [
    "The Honourable Mr ", "The Honourable Mrs ", "The Honourable Dr ",
    "The Honourable Miss ", "The Honourable Ms ", "The Honourable Inche ",
    "The Honourable Encik ", "The Honourable ",
    "The Hon. Mr ", "The Hon. Mrs ", "The Hon. Dr ",
    "The Hon. Miss ", "The Hon. Ms ", "The Hon. Inche ",
    "The Hon. ",
    "Assoc. Prof. ", "Assoc Prof ",
    "Er Dr ", "Er ",
    "BG (NS) ", "BG [NS] ", "MG [NS] ", "MG (NS) ",
    "RAdm (NS) ", "RAdm ",
    "BG ", "MG ",
    "Prof. ", "Prof ",
    "Maj. ", "Maj ",
    "Dr. ", "Dr, ", "Mr. ", "Mr, ", "Mi. ", "mr ", "Dr ", "Mr ", "Mrs ", "Miss ", "Ms ", "Mdm ", "Madam ",
    "Inche ", "Encik ", "Sir ", "Dato ", "Tun Dato ", "Tun ",
    "Asst Prof ", "Asst. Prof. ",
    "Tuan Haji ", "Haji ", "Hj. ", "Hj ",
    "Cdre ", "[NS] ", "(NS) ",
]

# Trailing comma-separated ALL-CAPS honorific abbreviations.
# Each token may have spaces within it (e.g. "J. P." counts as one token).
_HONORIFIC_SUFFIX_RE = re.compile(r"(?:,\s*[A-Z][A-Z.]*(?:\s+[A-Z][A-Z.]*)*)+$")

# Islamic suffix like "Al-Haj", "Al-Hajj" that can follow the name after a space.
_ISLAMIC_SUFFIX_RE = re.compile(r"\s+[Aa]l-[Hh]aj[jh]?\s*$")

# Trailing official role suffix: ", Financial Secretary", ", Attorney-General", etc.
# Applied before _HONORIFIC_SUFFIX_RE so that mixed-case role titles don't block
# the all-caps honorific stripping (e.g. "Hart, C.M.G., Financial Secretary" ->
# strip role -> "Hart, C.M.G." -> strip honorific -> "Hart").
_OFFICIAL_ROLE_SUFFIX_RE = re.compile(
    r",\s*(?:Acting\s+)?(?:Financial|Chief|Colonial)\s+Secretary"
    r"|,\s*Attorney[-\s]General"
    r"|,\s*(?:Acting\s+)?Governor\b",
    re.I,
)

# Title suffixes that can appear at the end of inverted names: "Surname, Firstname, Dr".
_INVERTED_TITLE_SUFFIXES = {"Dr", "Mdm", "Mr", "Mrs", "Ms", "Prof", "Assoc Prof", "RAdm", "BG"}

_MIN_SURNAME_LOOKUP_LENGTH = 2
_MIN_PREFIX_WORD_COUNT = 2
_MIN_MULTIWORD_SURNAME_LENGTH = 2
_MIN_REARRANGEABLE_WORD_COUNT = 3


def normalize_name(name: str) -> str:
    """
    Normalise a name string for storage and lookup:
    1. Collapse spaces between consecutive initials: "E. W. Barker" -> "E.W. Barker"
    2. Normalise Malay abbreviation: "Mohd." -> "Mohd"
    Note: lone-initial period ("S. Iswaran") is NOT stripped because some Speaker.name
    values keep the period (e.g. "A. Rahim Ishak") while others omit it ("S Iswaran").
    """
    name = re.sub(r"(?<=[A-Z]\.) (?=[A-Z]\.)", "", name)
    name = re.sub(r"\bMohd\.", "Mohd", name)
    return name


def _normalize_for_lookup(name: str) -> str:
    normalized = normalize_name(name)
    # Additional normalization for inverted-lookup key only:
    # strip period from a lone leading initial ("S. Name" -> "S Name") so that
    # "S. Rajaratnam" matches the lookup key for "Rajaratnam, S" (stored without period).
    # This does NOT affect the stored speaker_name -- only the lookup search key.
    normalized = re.sub(r"^([A-Z])\. (?=[A-Z])", r"\1 ", normalized)
    return normalized.lower()


def _period_normalize(name: str) -> str:
    """
    Normalize for period-stripped key comparison:
    'M.K.A. Jabbar' -> 'm k a jabbar'
    'J.B. Jeyaretnam' -> 'j b jeyaretnam'
    'S. Jayakumar' -> 's jayakumar'
    'Harun bin A. Ghani' -> 'harun bin a ghani'
    """
    # Insert space between consecutive uppercase initials using lookbehind/lookahead
    # so all pairs are split in one pass: "M.K.A." -> "M K A." (positions don't consume).
    normalized = re.sub(r"(?<=[A-Z])\.(?=[A-Z])", " ", name)
    normalized = re.sub(r"([A-Z])\.", r"\1", normalized)   # strip remaining trailing period: "K." -> "K"
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().lower()


def _strip_bin(name: str) -> str:
    """Remove the Malay 'bin'/'binte' patronymic connector (case-insensitive)."""
    return re.sub(r"\s+bin(?:te)?\s+", " ", name, flags=re.IGNORECASE).strip()


def _strip_middle_haji(name: str) -> str:
    """Remove 'Haji'/'Tuan Haji' from the middle of a name (not as a prefix).
    Used as a lookup fallback: 'Saidi Haji Shariff' -> 'Saidi Shariff'."""
    return re.sub(r"\s+(?:[Tt]uan\s+)?[Hh]aji\s+", " ", name).strip()


def _spelling_normalize(name: str) -> str:
    """
    Normalise common spelling variants for lookup purposes only:
    - Mohamad/Mohammed/Mohammad -> Mohamed
    - Consecutive spaced single uppercase letters -> joined: "B P M" -> "BPM"
    - Hyphens -> spaces (to match "Lee Siew-Choh" against "Lee Siew Choh")
    """
    normalized = re.sub(r"\bMohamad\b|\bMohammed\b|\bMohammad\b", "Mohamed", name)
    normalized = normalized.replace("-", " ")
    # Collapse sequences of spaced single uppercase letters: "B P M" -> "BPM"
    normalized = re.sub(
        r"\b([A-Z])((?:\s+[A-Z])+)\b",
        lambda abbrev_match: abbrev_match.group(1) + abbrev_match.group(2).replace(" ", ""),
        normalized,
    )
    return re.sub(r"\s+", " ", normalized).strip()


def _invert_to_natural(speaker_name: str) -> Optional[str]:
    """Convert 'Surname, Firstname[, TitleSuffix]' to natural 'Firstname Surname' form.
    Returns None if the name is not in inverted format."""
    if ", " not in speaker_name:
        return None
    parts = speaker_name.split(", ")
    if len(parts) >= 3 and parts[-1] in _INVERTED_TITLE_SUFFIXES:
        rest = " ".join(parts[1:-1])
    else:
        rest = ", ".join(parts[1:])
    return strip_title(f"{rest} {parts[0]}").strip()


def _wordset_key(name: str) -> tuple[frozenset, int]:
    words = _period_normalize(name).split()
    return frozenset(words), len(words)


def strip_title(text: str) -> str:
    while True:
        for prefix in _TITLE_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        else:
            return text


def infer_parliament(sitting: Sitting) -> Optional[int]:
    if sitting.parlement_no is not None:
        return sitting.parlement_no
    return VOLUME_TO_PARLIAMENT.get(sitting.volume_no)  # type: ignore[arg-type]


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
        key = (_period_normalize(speaker.name), speaker.parliament_number)
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
        key = (_period_normalize(_strip_bin(speaker.name)), speaker.parliament_number)
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
            natural_stripped = _invert_to_natural(speaker.name)
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
        natural = _invert_to_natural(speaker.name)
        if natural:
            triples.append((natural, speaker.name, speaker.parliament_number))
        triples.append((speaker.name, speaker.name, speaker.parliament_number))
    counts: dict[tuple[frozenset, int, int], int] = {}
    entries: list[tuple[tuple[frozenset, int, int], str]] = []
    for display, canonical_name, parliament in triples:
        words = _period_normalize(display).split()
        key = (frozenset(words), len(words), parliament)
        counts[key] = counts.get(key, 0) + 1
        entries.append((key, canonical_name))
    wordset: dict[tuple[frozenset, int, int], str] = {}
    for key, canonical_name in entries:
        if counts[key] == 1 and key not in wordset:
            wordset[key] = canonical_name
    return wordset


def _build_wordset_subset_lookup(speakers: list[Speaker]) -> dict[tuple[frozenset, int], str]:
    """Like _build_wordset_lookup but keyed by (frozenset(words), parliament) without word count.
    Only emits entries for names with 3+ words (after title stripping) to avoid false positives.
    Allows matching names where the word count differs, e.g. "Aline Wong" matching "Wong Aline K".
    """
    _MIN_WORDSET_SUBSET_WORDS = 3
    triples: list[tuple[str, str, int]] = []
    for speaker in speakers:
        natural = _invert_to_natural(speaker.name)
        if natural:
            triples.append((natural, speaker.name, speaker.parliament_number))
        triples.append((speaker.name, speaker.name, speaker.parliament_number))
    counts: dict[tuple[frozenset, int], int] = {}
    entries: list[tuple[tuple[frozenset, int], str]] = []
    for display, canonical_name, parliament in triples:
        words = _period_normalize(strip_title(display)).split()
        if len(words) < _MIN_WORDSET_SUBSET_WORDS:
            continue
        words = [w for w in words if len(w) > 1]
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
        natural = _invert_to_natural(speaker.name)
        if natural:
            forms.append((natural, speaker.name, speaker.parliament_number))
        forms.append((speaker.name, speaker.name, speaker.parliament_number))
    prefix_counts: dict[tuple[str, int], int] = {}
    prefix_entries: list[tuple[tuple[str, int], str]] = []
    for display, canonical, parliament in forms:
        words = _period_normalize(display).split()
        for prefix_length in range(_MIN_PREFIX_WORD_COUNT, len(words)):
            prefix_str = " ".join(words[:prefix_length])
            prefix_key = (prefix_str, parliament)
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
        natural = _invert_to_natural(speaker.name) or speaker.name
        words = _period_normalize(natural).split()
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


def _parse_name_and_location(text: str) -> tuple[str, Optional[str]]:
    """
    Extract (speaker_name, location_name) from text like:
      "Name, Honorifics (Constituency), Portfolio [possibly (more)]"
      "Name (Constituency)"
      "Name, Honorifics"   (no constituency)

    Uses the FIRST parenthetical as constituency, not the last, so that
    portfolio suffixes like ", Second Deputy Prime Minister (Foreign Affairs)"
    do not clobber the constituency.
    """
    text = text.strip().rstrip(". ")

    first_open = text.find("(")
    if first_open != -1:
        # Walk forward to find matching close paren (handles nesting)
        depth = 0
        close_idx = -1
        for char_index in range(first_open, len(text)):
            if text[char_index] == "(":
                depth += 1
            elif text[char_index] == ")":
                depth -= 1
                if depth == 0:
                    close_idx = char_index
                    break
        if close_idx != -1:
            constituency = text[first_open + 1 : close_idx].strip()
            name_part = text[:first_open].rstrip(", ")
        else:
            # No matching close paren — constituency is truncated; use text before "("
            constituency = None
            name_part = text[:first_open].rstrip(", )")
    else:
        constituency = None
        name_part = text

    name = strip_title(name_part.strip())
    name = _OFFICIAL_ROLE_SUFFIX_RE.sub("", name).rstrip(", ").strip()
    name = _HONORIFIC_SUFFIX_RE.sub("", name).rstrip(", ").strip()
    # Strip trailing Islamic honorific suffix: "Rahmat Bin Kenap Al-Haj" -> "Rahmat Bin Kenap"
    name = _ISLAMIC_SUFFIX_RE.sub("", name).strip()
    return name, constituency


def _parse_speaker_line(line: str) -> tuple[str, Optional[str]]:
    """
    Parse SPEAKER lines: "[Title] SPEAKER ([Title] Name [(Constituency)]).".
    Extracts the name and constituency from within the outer parentheses.
    """
    line = line.rstrip(". ")
    # Find the outermost parenthetical (greedy: first '(' to last ')')
    match = re.search(r"\((.+)\)\s*$", line)
    if not match:
        return "SPEAKER", None
    inner = match.group(1).strip()
    inner_stripped = strip_title(inner)
    return _parse_name_and_location(inner_stripped)


def _parse_entry_line(line: str) -> Optional[tuple[str, Optional[str]]]:
    line = line.strip()
    if not line:
        return None
    # Strip bullet prefix for modern vol 88-89 (## Present: / ## Absent: format)
    if line.startswith("* "):
        line = line[2:].strip()
    if not line:
        return None
    # Strip markdown bold prefix: "**Mr Ng Kah Ting" -> "Mr Ng Kah Ting"
    if line.startswith("**"):
        line = line[2:].strip()
    # Strip stray section-label prefix: "Absent: Mr Ahmad Mohd Magad" -> "Mr Ahmad Mohd Magad"
    line = re.sub(r"^(?:Absent|Present):\s*", "", line, flags=re.IGNORECASE)
    if not line:
        return None
    # Strip leading OCR digit artifacts: "2Mr" -> "Mr"
    line = re.sub(r"^\d+(?=[A-Z])", "", line)

    if "SPEAKER" in line:
        return _parse_speaker_line(line)

    return _parse_name_and_location(strip_title(line))


def _extract_section_lines(content: str, section: str) -> list[str]:
    """
    Extract non-empty entry lines from a PRESENT or ABSENT section.
    Handles both standard ("PRESENT:") and modern ("## Present:") headers.
    """
    lines = content.split("\n")
    in_section = False
    other = "ABSENT" if section == "PRESENT" else "PRESENT"
    result = []

    for line in lines:
        stripped = line.strip()

        if not in_section:
            # Detect section header: "PRESENT:", "**PRESENT:**", or "## Present:"
            if re.match(rf"^(?:\*{{2}}|#+)?\s*{section}\s*:(?:\*{{2}})?\s*$", stripped, re.IGNORECASE):
                in_section = True
            continue

        # End-of-section markers
        if re.match(rf"^(?:\*{{2}}|#+)?\s*{other}\s*:(?:\*{{2}})?\s*$", stripped, re.IGNORECASE):
            break
        if stripped.startswith("####") or stripped.startswith("# ") or stripped == "* * *":
            break
        # Numbered oral-question marker ("1\. **Mr X asked...") signals section end.
        if re.match(r"^\d+\\\.?\s", stripped):
            break

        if stripped:
            result.append(line)

    return result


def _try_name_variant(
    name: str,
    parliament: int,
    lookups: SpeakerLookups,
    include_wordset: bool = True,
) -> Optional[str]:
    normalized = _period_normalize(name)
    bin_normalized = _period_normalize(_strip_bin(name))
    result = (
        lookups.direct.get((normalized, parliament))
        or lookups.bin_free.get((bin_normalized, parliament))
        or lookups.direct.get((bin_normalized, parliament))
    )
    if result:
        return result
    if include_wordset:
        result = lookups.wordset.get((*_wordset_key(name), parliament))
        if result:
            return result
        _wss_words = [w for w in _period_normalize(name).split() if len(w) > 1]
        result = lookups.wordset_subset.get((frozenset(_wss_words), parliament))
        if result:
            return result
    return lookups.prefix.get((normalized, parliament))


def resolve_canonical_name(name: str, parliament: int, lookups: SpeakerLookups) -> Optional[str]:
    """
    Try to match a name string to canonical Speaker.name using the full lookup cascade.
    Returns canonical Speaker.name if found, None if no match.
    Reusable by any module that needs speaker name resolution.
    """
    # Apply parliament-agnostic OCR corrections before any parliament-scoped lookup.
    corrected = _OCR_FORM_TO_CORRECTED_NAME.get(_period_normalize(name))
    if corrected:
        name = corrected
    canonical = _NAME_PARLIAMENT_TO_CANONICAL_SPEAKER.get((_period_normalize(name), parliament))
    if canonical:
        return canonical
    canonical = lookups.inverted.get((_normalize_for_lookup(name), parliament))
    if canonical:
        return canonical
    canonical = _try_name_variant(name, parliament, lookups)
    if canonical:
        return canonical

    spelled = _spelling_normalize(name)
    if spelled != name:
        canonical = _try_name_variant(spelled, parliament, lookups)
        if canonical:
            return canonical

    no_haji = _strip_middle_haji(name)
    if no_haji != name:
        canonical = _try_name_variant(no_haji, parliament, lookups, include_wordset=False)
        if canonical:
            return canonical

    # CamelCase split fallback for source markdown that concatenated names without
    # spaces ("AbdullahTarmugi"). Re-strip title after splitting in case the missing
    # space prevented strip_title from matching at extraction time.
    split = re.sub(r"([a-z\.])([A-Z])", r"\1 \2", name)
    if split != name:
        split_stripped = strip_title(split).strip()
        canonical = (
            _NAME_PARLIAMENT_TO_CANONICAL_SPEAKER.get((_period_normalize(split_stripped), parliament))
            or _try_name_variant(split_stripped, parliament, lookups)
        )
        if canonical:
            return canonical

    # Surname-only fallback: if name reduces to a single token, try it as the unique
    # last name in this parliament.  Only fires for unambiguous cases.
    words_pn = _period_normalize(name).split()
    if len(words_pn) == 1:
        return lookups.surname_fallback.get((words_pn[0], parliament))
    return None


def get_sitting_attendance(sitting: Sitting, lookups: SpeakerLookups) -> list[Attendance]:
    if not sitting.markdown_content:
        return []

    parliament = infer_parliament(sitting)
    content = sitting.markdown_content
    records = []

    for section, is_present in [("PRESENT", True), ("ABSENT", False)]:
        for line in _extract_section_lines(content, section):
            parsed = _parse_entry_line(line)
            if not parsed:
                continue
            name, location = parsed
            if not name:
                continue
            name = normalize_name(name)
            if parliament is not None:
                canonical = resolve_canonical_name(name, parliament, lookups)
                if canonical:
                    name = canonical
            records.append(Attendance(
                sitting_id=sitting.id,
                speaker_name=name,
                is_present=is_present,
                location_name=location,
            ))

    return records
