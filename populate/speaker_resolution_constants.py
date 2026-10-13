from datetime import date

# Office holders by date: (first day, last day, name). Names resolve through the
# Speaker lookups in the row's parliament, with the colonial fallback for parliament 0.
# A bare role string links only when exactly one holder was in office that day.
# Sources: parliament.gov.sg Speaker page (names and years) and the Wikipedia list of
# Speakers and Deputy Speakers (exact dates); see docs/adr/0002.
SPEAKER_TERMS: list[tuple[date, date, str]] = [
    (date(1955, 4, 22), date(1963, 9, 3), "George Oehlers"),
    (date(1963, 10, 22), date(1964, 10, 30), "E.W. Barker"),
    (date(1964, 11, 2), date(1966, 8, 5), "A.P. Rajah"),
    (date(1966, 8, 17), date(1970, 1, 18), "Coomaraswamy, P."),
    (date(1970, 1, 27), date(1988, 8, 17), "Yeoh Ghim Seng"),
    (date(1989, 1, 9), date(2001, 10, 17), "Tan Soo Khoon"),
    (date(2002, 3, 22), date(2011, 4, 18), "Abdullah Bin Tarmugi"),
    (date(2011, 10, 10), date(2012, 12, 12), "Michael Palmer"),
    (date(2013, 1, 14), date(2017, 8, 7), "Halimah Yacob"),
    (date(2017, 9, 11), date(2023, 7, 17), "Tan Chuan-Jin"),
]

# Two Deputy Speakers served at once for most of Parliaments 7, 10, 11 and 12, so a
# bare "Mr Deputy Speaker" on those dates stays unlinked unless the string names the person.
DEPUTY_SPEAKER_TERMS: list[tuple[date, date, str]] = [
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
]

# Deputy Speakers Hansard addresses as "Mdm"; the parliament.gov.sg list for 1955 to 2011 names no other woman.
DEPUTY_SPEAKER_WOMEN: set[str] = {"Lim Hwee Hua", "Indranee Rajah"}

# Role-only strings whose holder changed mid-parliament, by date. Sources disagree on
# whether Lim Yew Hock took over on 7 or 8 June 1956, so that sitting stays unlinked.
# Prime Minister handovers (28 Nov 1990, 12 Aug 2004) fell on days without a sitting.
DATED_ROLE_TERMS: dict[str, list[tuple[date, date, str]]] = {
    "The Chief Minister": [
        (date(1955, 4, 6), date(1956, 6, 6), "David Marshall"),
        (date(1956, 6, 8), date(1959, 6, 3), "Lim Yew Hock"),
    ],
    "The Prime Minister": [
        (date(1959, 6, 5), date(1990, 11, 27), "Lee Kuan Yew"),
        (date(1990, 11, 28), date(2004, 8, 11), "Goh Chok Tong"),
        (date(2004, 8, 12), date(2024, 5, 14), "Lee Hsien Loong"),
    ],
}

ROLE_ONLY_SPEAKERS: dict[tuple[str, int], str] = {
    ("The Minister for Health", 11): "Khaw Boon Wan",
}

NON_SPEAKERS: set[str] = {
    "An hon. Member",
    "Some hon. Members",
    "Non-Residents",
    "Tributes by Leader of the House and Opposition Leaders",
}

COLONIAL_PARLIAMENT_FALLBACKS: list[int] = [1, 2, 3]

