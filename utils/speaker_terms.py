from datetime import date

# Sources: parliament.gov.sg, Wikipedia, Hansard Speaker elections
SPEAKER_TERMS: tuple[tuple[date, date, str], ...] = (
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
    (date(2023, 8, 2), date(2025, 4, 15), "Seah Kian Peng"),
    # TODO: set the end date when the 15th Parliament is dissolved
    (date(2025, 9, 5), date.max, "Seah Kian Peng"),
)
