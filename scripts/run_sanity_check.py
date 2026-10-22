import json
from typing import Optional

from sqlmodel import Session

from crud.hansard_website_response import CRUDHansardWebsiteResponse
from crud.report import CRUDReport
from database.init import engine
from database.report import Report
from logs import logger
from services.report import build_report
from services.speech import get_speeches, get_start_of_speech_line

_SAMPLE_FILE_PATH = "sample.json"
_SEPARATOR_WIDTH = 90
_SNIPPET_LENGTH = 500
_SNIPPET_LINES_SHOWN = 15
_PERCENT = 100


def _get_start_line(report: Report) -> Optional[int]:
    if not report.markdown_content:
        return None
    return get_start_of_speech_line(
        report.markdown_content,
        report.title,
        report.subtitle,
        report.original_title,
        report.report_type,
        report.report_version,
    )


def run() -> None:
    with open(_SAMPLE_FILE_PATH) as sample_file:
        sample_sets = json.load(sample_file)

    report_ids = (
        sample_sets.get("pilot", [])
        + sample_sets.get("held_out", [])
        + sample_sets.get("regression", [])
    )

    with Session(engine) as session:
        stored_reports = CRUDReport(session).get_by_ids(report_ids)
        report_id_strings = {stored_report.report_id for stored_report in stored_reports}

        website_responses = CRUDHansardWebsiteResponse(session).get_by_report_ids(report_id_strings)
    report_id_to_website_response = {website_response.report_id: website_response for website_response in website_responses}

    logger.info(f"Sample Report IDs:       {len(report_ids)}")
    logger.info(f"Stored Reports found:    {len(stored_reports)}")
    logger.info(f"Matching HWRs found:     {len(website_responses)}")
    logger.info("")

    issues = []
    stats = {
        "total": 0,
        "no_website_response": 0,
        "no_content": 0,
        "no_markdown": 0,
        "no_start_line": 0,
        "no_speeches": 0,
        "invalid_speeches": 0,
        "title_mismatch": 0,
        "subtitle_mismatch": 0,
        "pass": 0,
    }

    logger.info(f"{'report_id':<14} {'type':<22} {'md':>2} {'sl':>2} {'sp':>4} {'v':>2}  checks")
    logger.info("-" * _SEPARATOR_WIDTH)

    for stored in sorted(stored_reports, key=lambda stored_report: stored_report.report_type):
        website_response = report_id_to_website_response.get(stored.report_id)
        stats["total"] += 1

        if website_response is None:
            stats["no_website_response"] += 1
            issues.append(f"[NO HWR]  report_id={stored.report_id} type={stored.report_type}")
            logger.info(f"{stored.report_id:<14} {stored.report_type:<22} {'?':>2} {'?':>2} {'?':>4} {'?':>2}  NO HansardWebsiteResponse found")
            continue

        if website_response.content is None:
            stats["no_content"] += 1
            logger.info(f"{stored.report_id:<14} {stored.report_type:<22} {'-':>2} {'-':>2} {'-':>4} {'-':>2}  no content (expected for some types)")
            continue

        regenerated_report = build_report(website_response)

        checks = []
        is_failed = False

        if regenerated_report.markdown_content is None:
            stats["no_markdown"] += 1
            checks.append("NO_MARKDOWN")
            is_failed = True
        markdown_flag = "Y" if regenerated_report.markdown_content else "N"

        if regenerated_report.title != stored.title:
            stats["title_mismatch"] += 1
            checks.append(f"TITLE_MISMATCH(stored={stored.title!r} regen={regenerated_report.title!r})")
            is_failed = True

        if regenerated_report.subtitle != stored.subtitle:
            stats["subtitle_mismatch"] += 1
            checks.append(f"SUBTITLE_MISMATCH(stored={stored.subtitle!r} regen={regenerated_report.subtitle!r})")
            is_failed = True

        start_line = _get_start_line(regenerated_report)
        if start_line is None and regenerated_report.markdown_content:
            stats["no_start_line"] += 1
            checks.append("NO_START_LINE")
            is_failed = True

        speeches = []
        speech_count = "-"
        valid_flag = "-"
        if start_line is not None:
            speeches = get_speeches(
                regenerated_report.markdown_content, start_line, regenerated_report.report_type, regenerated_report.report_version
            )
            speech_count = str(len(speeches))
            if len(speeches) == 0:
                stats["no_speeches"] += 1
                checks.append("NO_SPEECHES")
                is_failed = True
            else:
                invalid = [speech for speech in speeches if not speech.speaker or not speech.transcript.strip()]
                if invalid:
                    stats["invalid_speeches"] += 1
                    checks.append(f"INVALID_SPEECHES({len(invalid)})")
                    is_failed = True
            valid_flag = "Y" if not is_failed else "N"

        if not is_failed:
            stats["pass"] += 1
            checks.append("OK")

        start_line_flag = "Y" if start_line is not None else "N"
        checks_text = "  ".join(checks)
        logger.info(f"{stored.report_id:<14} {stored.report_type:<22} {markdown_flag:>2} {start_line_flag:>2} {speech_count:>4} {valid_flag:>2}  {checks_text}")

        if is_failed:
            issues.append({
                "report_id": stored.report_id,
                "report_type": stored.report_type,
                "checks": checks,
                "title_stored": stored.title,
                "title_regen": regenerated_report.title,
                "subtitle_stored": stored.subtitle,
                "subtitle_regen": regenerated_report.subtitle,
                "start_line": start_line,
                "speech_count": len(speeches),
                "markdown_snippet": (regenerated_report.markdown_content or "")[:_SNIPPET_LENGTH],
            })

    logger.info("")
    logger.info("=" * _SEPARATOR_WIDTH)
    logger.info(f"Total records:         {stats['total']}")
    logger.info(f"No matching HWR:       {stats['no_website_response']}")
    logger.info(f"No content:            {stats['no_content']}")
    logger.info(f"No markdown generated: {stats['no_markdown']}")
    logger.info(f"No start line:         {stats['no_start_line']}")
    logger.info(f"No speeches:           {stats['no_speeches']}")
    logger.info(f"Invalid speeches:      {stats['invalid_speeches']}")
    logger.info(f"Title mismatches:      {stats['title_mismatch']}")
    logger.info(f"Subtitle mismatches:   {stats['subtitle_mismatch']}")
    logger.info(f"PASS:                  {stats['pass']}")
    logger.info("")

    content_records = stats["total"] - stats["no_website_response"] - stats["no_content"]
    if content_records > 0:
        pass_rate = stats["pass"] / content_records * _PERCENT
        logger.info(f"Pass rate (content records): {stats['pass']}/{content_records} = {pass_rate:.1f}%")

    if issues:
        logger.info("")
        logger.info("=== ISSUE DETAILS ===")
        for issue in issues:
            if isinstance(issue, str):
                logger.info(f"\n  {issue}")
                continue
            logger.info(f"\n  report_id={issue['report_id']}  type={issue['report_type']}")
            logger.info(f"  checks: {issue['checks']}")
            if "TITLE_MISMATCH" in str(issue["checks"]):
                logger.info(f"  title stored: {issue['title_stored']!r}")
                logger.info(f"  title regen:  {issue['title_regen']!r}")
            if "SUBTITLE_MISMATCH" in str(issue["checks"]):
                logger.info(f"  subtitle stored: {issue['subtitle_stored']!r}")
                logger.info(f"  subtitle regen:  {issue['subtitle_regen']!r}")
            if "NO_START_LINE" in str(issue["checks"]) or "NO_SPEECHES" in str(issue["checks"]):
                logger.info("  markdown snippet:")
                for line in issue["markdown_snippet"].splitlines()[:_SNIPPET_LINES_SHOWN]:
                    logger.info(f"    {line}")


if __name__ == "__main__":
    run()
