from datetime import date

# NOTE: Hansard prints "Mdm Speaker" for her; every other Speaker in SPEAKER_TERMS is a man.
SPEAKER_WOMEN: frozenset[str] = frozenset({"Halimah Yacob"})

# NOTE: two Deputy Speakers served at once for most of Parliaments 7, 10, 11, 12, 13, 14 and 15, so a bare "Mr Deputy Speaker" on those dates stays unlinked unless the string names the person.
# Sources: same as SPEAKER_TERMS; Parliaments 13, 14 and 15 from the Hansard sittings of 25 January 2016, 31 August 2020 and 22 September 2025 ("Election of Deputy Speakers"), the Wikipedia Deputy Speaker page and the 13th and 14th Parliament pages (terms end at dissolution)
DEPUTY_SPEAKER_TERMS: tuple[tuple[date, date, str], ...] = (
    (date(1955, 4, 26), date(1959, 3, 31), "Lim, R.C.H."),
    (date(1959, 7, 15), date(1961, 9, 24), "G. Kandasamy"),
    (date(1961, 11, 16), date(1963, 9, 3), "John Mammen"),
    (date(1963, 12, 9), date(1965, 12, 9), "Fong Kim Heng"),
    (date(1966, 2, 23), date(1966, 8, 16), "Coomaraswamy, P."),
    (date(1968, 7, 11), date(1970, 1, 26), "Yeoh Ghim Seng"),
    (date(1972, 11, 22), date(1976, 12, 5), "Tang See Chim"),
    (date(1977, 2, 22), date(1980, 12, 4), "Tang See Chim"),
    (date(1981, 3, 6), date(1984, 12, 3), "Hwang Soo Jin"),
    (date(1985, 3, 6), date(1988, 8, 17), "Tan Soo Khoon"),
    (date(1989, 1, 16), date(1991, 8, 13), "Lim Boon Heng"),
    (date(1989, 1, 16), date(1991, 8, 13), "Abdullah Bin Tarmugi"),
    (date(1992, 1, 13), date(1993, 6, 30), "Abdullah Bin Tarmugi"),
    (date(1993, 2, 26), date(1996, 12, 15), "Yap Giau Cheng, Eugene"),
    (date(1997, 6, 2), date(2001, 10, 17), "Yap Giau Cheng, Eugene"),
    (date(2002, 4, 1), date(2004, 8, 11), "Lim Hwee Hua"),
    (date(2002, 4, 1), date(2006, 4, 19), "Chew Heng Ching"),
    (date(2004, 9, 1), date(2006, 4, 19), "S Iswaran"),
    (date(2006, 11, 8), date(2011, 4, 18), "Indranee Rajah"),
    (date(2006, 11, 8), date(2011, 4, 18), "Matthias Yao Chih"),
    (date(2011, 10, 17), date(2015, 8, 24), "Seah Kian Peng"),
    (date(2011, 10, 17), date(2015, 8, 24), "Charles Chong"),
    (date(2016, 1, 25), date(2020, 6, 23), "Charles Chong"),
    (date(2016, 1, 25), date(2020, 6, 23), "Lim Biow Chuan"),
    (date(2020, 8, 31), date(2025, 4, 15), "Jessica Tan Soon Neo"),
    (date(2020, 8, 31), date(2025, 4, 15), "Christopher de Souza"),
    # TODO: set the end dates when the 15th Parliament is dissolved
    (date(2025, 9, 22), date.max, "Christopher de Souza"),
    (date(2025, 9, 22), date.max, "Xie Yao Quan"),
)

# NOTE: Hansard addresses these Deputy Speakers as "Mdm"; the parliament.gov.sg list for 1955 to 2011 and the Wikipedia Deputy Speaker page name no other woman.
DEPUTY_SPEAKER_WOMEN: frozenset[str] = frozenset({"Lim Hwee Hua", "Indranee Rajah", "Jessica Tan Soon Neo"})

# NOTE: sources disagree on whether Lim Yew Hock took over on 7 or 8 June 1956. The sitting of 7 June names David Marshall as Chief Minister throughout (its attendance list and the header of every report he speaks in), so his term runs through that day. Prime Minister handovers fell on days without a sitting.
# Sources: Al Jazeera 15 May 2024; pmo.gov.sg
DATED_ROLE_TERMS: dict[str, tuple[tuple[date, date, str], ...]] = {
    "The Chief Minister": (
        (date(1955, 4, 6), date(1956, 6, 7), "David Marshall"),
        (date(1956, 6, 8), date(1959, 6, 3), "Lim Yew Hock"),
    ),
    "The Prime Minister": (
        (date(1959, 6, 5), date(1990, 11, 27), "Lee Kuan Yew"),
        (date(1990, 11, 28), date(2004, 8, 11), "Goh Chok Tong"),
        (date(2004, 8, 12), date(2024, 5, 14), "Lee Hsien Loong"),
        # TODO: set the end date when the term ends
        (date(2024, 5, 15), date.max, "Lawrence Wong"),
    ),
}

# Sources: Wikipedia day-level dates citing NewspaperSG, Straits Times
HEAD_OF_STATE_TERMS: dict[str, tuple[tuple[date, date, str], ...]] = {
    "His Excellency the Governor": (
        (date(1952, 4, 21), date(1955, 6, 1), "John Nicoll"),
        (date(1955, 6, 2), date(1955, 6, 29), "William Goode"),
        (date(1955, 6, 30), date(1957, 12, 8), "Robert Black"),
        (date(1957, 12, 9), date(1959, 6, 2), "William Goode"),
    ),
    "His Excellency the Yang di-Pertuan Negara": (
        (date(1959, 6, 3), date(1959, 12, 2), "William Goode"),
        (date(1959, 12, 3), date(1965, 8, 8), "Yusof bin Ishak"),
    ),
    "The President": (
        (date(1965, 8, 9), date(1970, 11, 22), "Yusof bin Ishak"),
        (date(1971, 1, 2), date(1981, 5, 11), "Benjamin Henry Sheares"),
        (date(1981, 10, 23), date(1985, 3, 27), "C.V. Devan Nair"),
        (date(1985, 9, 2), date(1993, 8, 31), "Wee Kim Wee"),
        (date(1993, 9, 1), date(1999, 8, 31), "Ong Teng Cheong"),
        (date(1999, 9, 1), date(2011, 8, 31), "S R Nathan"),
        (date(2011, 9, 1), date(2017, 8, 31), "Tan Keng Yam, Tony"),
        (date(2017, 9, 14), date(2023, 9, 13), "Halimah Yacob"),
        # TODO: set the end date when the term ends
        (date(2023, 9, 14), date.max, "Tharman Shanmugaratnam"),
    ),
}

ROLE_ONLY_SPEAKERS: dict[tuple[str, int], str] = {
    ("The Minister for Health", 11): "Khaw Boon Wan",
}

NON_SPEAKERS: frozenset[str] = frozenset(
    {
        "An hon. Member",
        "Some hon. Members",
        "Non-Residents",
        "Tributes by Leader of the House and Opposition Leaders",
    }
)

COLONIAL_PARLIAMENT_FALLBACKS: tuple[int, ...] = (1, 2, 3)

COLONIAL_PARLIAMENT_NUMBER = 0
