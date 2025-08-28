from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

from database.report import Report


def get_mps_speaking(report: Report) -> Optional[str]:
    if report.markdown_content is None:
        return None
    if report.content is None:
        return None
    for line in report.markdown_content.splitlines():
        if line.startswith("MPs Speaking:|"):
            return line

    soup = BeautifulSoup(report.content, "html.parser")
    meta = soup.find("meta", {"name": "MP_Speak"})
    if meta is None:
        return None
    if meta.get("content") is None:
        return None
    return meta.get("content")


# def get_strata_sample():
#     session = next(get_session())
#     strata_sample: list[Report] = []
#     MAX_PARLIAMENT_NUMBER = 12
#     for parliament_number in range(MAX_PARLIAMENT_NUMBER):
#         for report_type_enum in ReportType:
#             sample = session.exec(
#                 select(Report)
#                 .where(Report.sitting_date < datetime(2012, 9, 10, 0, 0, 0, 0))
#                 .where(Report.content != None)
#                 .where(Report.report_type == report_type_enum.value)
#                 .where(Report.sitting_number == parliament_number)
#             ).first()
#             if sample is None:
#                 continue
#             strata_sample.append(sample)
#     return strata_sample
#
#
# sample = get_strata_sample()
# with open("sample.json", "w") as f:
#     data = json.dump([i.model_dump() for i in sample], f, default=str)
#
#

# with open("sample.json") as f:
#     data = json.load(f)
# reports = [Report(**i) for i in data]
#
#
# def get_start_of_speech_line(
#     markdown_content: str, title: str, subtitle: Optional[str], id: int
# ) -> Optional[int]:
#     for i, line in enumerate(markdown_content.splitlines()):
#         if subtitle:
#             if subtitle in line:
#                 return i
#         if title in line:
#             return i
#     print(id)
#     return None
#
#
# output = [
#     get_start_of_speech_line(i.markdown_content, i.title, i.subtitle, i.id)
#     for i in reports
# ]
#
#
# print(output)


SAMPLE_TITLES = [
    "SUBSIDY AT POLYCLINICS",
    "Teachers Trained in Visual Arts, Music and Drama",
    "Public Service Broadcast (PSB) Funding and Viewership",
    "Supply of Sheep for Korban for Hari Raya Haji",
    "Lease of Farrer Park Swimming Complex to Private Entity",
    "Number and Profile of Homeless Persons",
    "Business Failure Rates amongst Singapore SMEs",
    "Assessment of Hazards at Incident Sites to Prevent SCDF Officers from Sustaining Injuries",
    "Update on National Research Foundation's Work",
    "MOTORCYCLISTS RIDING AND PARKING ON PEDESTRIAN PAVEMENTS (Action by police)",
    "Assessment of Hazards at Incident Sites to Prevent SCDF Officers from Sustaining Injuries",
    "Impact of Livestock Export Rule Changes on the Annual Observance of Korban in Singapore",
    "Impact of Changes in Minimum Salaries",
    "Availability of Space in JTC Facilities for SMEs",
    "Impact of Data Privacy Laws on Consumer Data and Data Residency",
    "Doctors in Public Service Freelancing in the Private Sector",
    "Ensuring Quality Early Childhood Education and Childcare Services",
    "Impact of Restrictions on Hiring of Foreign Workers",
    "Pre-school Education",
    "More Help for Households on Government Assistance Schemes and Those Living in Rental Flats",
    "Teachers Trained in Visual Arts, Music and Drama",
    "COMMITTEE OF SUPPLY REPORTING PROGRESS",
    "Impact of Recent Restrictions on Foreign Worker Numbers on SMEs",
    "Number and Profile of Unwed Mothers",
    "Attracting Singaporeans to Work in Shipping Industry",
    "Pregnancy and Maternity-related Complaints by Employees",
    "SPARK-accredited Pre-schools",
    "Singapore Citizens above the Age of 21 who are Resident in Singapore in 2000, 2005 and 2010",
    "Training Employees for the Silver Industry",
    "Government Measures to Contain Rising Costs and Help Lower Income Group",
    "Singapore Arts Festival",
    "Guidelines to Protect Lower Wage Workers from Wage Reductions",
    "Large Corporations Pulling Out of Sponsoring Local Sports Events",
    "Extension of Home Loan Term to 50 Years",
    "Singaporeans Suffering Poor Health",
    "Encouraging Overseas-trained Doctors to Return to Singapore",
    "Review of Government Procurement Processes",
    "SETTLEMENT OF HOSPITAL BILLS",
    "ELDERLY AND COMMUTERS WITH SPECIAL NEEDS (Transport policy)",
    "Disbursements of Zakat Collection Under Asnaf",
]


@dataclass
class ReportHeader:
    title: str
    subtitle: Optional[str] = None


def _has_no_subtitle(raw_title: str) -> bool:
    return raw_title[-1] != ")"


def get_title_and_subtitle(raw_title: str):
    if _has_no_subtitle(raw_title):
        return ReportHeader(title=raw_title)

    title = ""
    subtitle = None
    in_brackets_content = ""
    is_in_brackets = False

    for letter in raw_title:
        if letter == "(":
            is_in_brackets = True
            continue

        if is_in_brackets:
            if letter != ")":
                in_brackets_content += letter
                continue
            if not in_brackets_content.isupper():
                subtitle = f"({in_brackets_content})"
            else:
                title += f"({in_brackets_content})"

            in_brackets_content = ""
            is_in_brackets = False
            continue

        title += letter

    return ReportHeader(title=title, subtitle=subtitle)


test = [get_title_and_subtitle(i) for i in SAMPLE_TITLES]
for i in test:
    print(i)
