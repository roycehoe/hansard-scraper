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