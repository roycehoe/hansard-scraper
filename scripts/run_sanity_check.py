"""
Sanity check: HansardWebsiteResponse -> Report -> Speech.
Loads IDs from sample.json (Report IDs), finds matching HansardWebsiteResponses,
regenerates objects, and compares against the control (raw HTML content).
"""

import json

from crud.hansard_website_response import CRUDHansardWebsiteResponse
from crud.report import CRUDReport
from database.init import get_session
from services.report import build_report
from services.speech import get_speeches, get_start_of_speech_line


def run():
    with open("sample.json") as f:
        sample_sets = json.load(f)

    report_ids = (
        sample_sets.get("pilot", [])
        + sample_sets.get("held_out", [])
        + sample_sets.get("regression", [])
    )

    session = next(get_session())

    stored_reports = CRUDReport(session).get_by_ids(report_ids)
    report_id_strings = {r.report_id for r in stored_reports}

    hwrs = CRUDHansardWebsiteResponse(session).get_all_by_report_ids(report_id_strings)
    hwr_by_report_id = {h.report_id: h for h in hwrs}

    print(f"Sample Report IDs:       {len(report_ids)}")
    print(f"Stored Reports found:    {len(stored_reports)}")
    print(f"Matching HWRs found:     {len(hwrs)}")
    print()

    issues = []
    stats = {
        "total": 0,
        "no_hwr": 0,
        "no_content": 0,
        "no_markdown": 0,
        "no_start_line": 0,
        "no_speeches": 0,
        "invalid_speeches": 0,
        "title_mismatch": 0,
        "subtitle_mismatch": 0,
        "pass": 0,
    }

    print(f"{'report_id':<14} {'type':<22} {'md':>2} {'sl':>2} {'sp':>4} {'v':>2}  checks")
    print("-" * 90)

    for stored in sorted(stored_reports, key=lambda r: r.report_type):
        hwr = hwr_by_report_id.get(stored.report_id)
        stats["total"] += 1

        if hwr is None:
            stats["no_hwr"] += 1
            issues.append(f"[NO HWR]  report_id={stored.report_id} type={stored.report_type}")
            print(f"{stored.report_id:<14} {stored.report_type:<22} {'?':>2} {'?':>2} {'?':>4} {'?':>2}  NO HansardWebsiteResponse found")
            continue

        if hwr.content is None:
            stats["no_content"] += 1
            print(f"{stored.report_id:<14} {stored.report_type:<22} {'-':>2} {'-':>2} {'-':>4} {'-':>2}  no content (expected for some types)")
            continue

        regen = build_report(hwr)

        checks = []
        failed = False

        if regen.markdown_content is None:
            stats["no_markdown"] += 1
            checks.append("NO_MARKDOWN")
            failed = True
        md_flag = "Y" if regen.markdown_content else "N"

        if regen.title != stored.title:
            stats["title_mismatch"] += 1
            checks.append(f"TITLE_MISMATCH(stored={stored.title!r} regen={regen.title!r})")
            failed = True

        if regen.subtitle != stored.subtitle:
            stats["subtitle_mismatch"] += 1
            checks.append(f"SUBTITLE_MISMATCH(stored={stored.subtitle!r} regen={regen.subtitle!r})")
            failed = True

        start_line = None
        if regen.markdown_content:
            start_line = get_start_of_speech_line(
                regen.markdown_content,
                regen.title,
                regen.subtitle,
                regen.original_title,
                regen.report_type,
            )
        if start_line is None and regen.markdown_content:
            stats["no_start_line"] += 1
            checks.append("NO_START_LINE")
            failed = True

        speeches = []
        sp_count = "-"
        valid_flag = "-"
        if start_line is not None:
            speeches = get_speeches(regen.markdown_content, start_line, regen.report_type)
            sp_count = str(len(speeches))
            if len(speeches) == 0:
                stats["no_speeches"] += 1
                checks.append("NO_SPEECHES")
                failed = True
            else:
                invalid = [s for s in speeches if not s.speaker or not s.transcript.strip()]
                if invalid:
                    stats["invalid_speeches"] += 1
                    checks.append(f"INVALID_SPEECHES({len(invalid)})")
                    failed = True
            valid_flag = "Y" if not failed else "N"

        if not failed:
            stats["pass"] += 1
            checks.append("OK")

        sl_display = "Y" if start_line is not None else "N"
        check_str = "  ".join(checks)
        print(f"{stored.report_id:<14} {stored.report_type:<22} {md_flag:>2} {sl_display:>2} {sp_count:>4} {valid_flag:>2}  {check_str}")

        if failed:
            issues.append({
                "report_id": stored.report_id,
                "report_type": stored.report_type,
                "checks": checks,
                "title_stored": stored.title,
                "title_regen": regen.title,
                "subtitle_stored": stored.subtitle,
                "subtitle_regen": regen.subtitle,
                "start_line": start_line,
                "speech_count": len(speeches),
                "markdown_snippet": (regen.markdown_content or "")[:500],
            })

    print()
    print("=" * 90)
    print(f"Total records:         {stats['total']}")
    print(f"No matching HWR:       {stats['no_hwr']}")
    print(f"No content:            {stats['no_content']}")
    print(f"No markdown generated: {stats['no_markdown']}")
    print(f"No start line:         {stats['no_start_line']}")
    print(f"No speeches:           {stats['no_speeches']}")
    print(f"Invalid speeches:      {stats['invalid_speeches']}")
    print(f"Title mismatches:      {stats['title_mismatch']}")
    print(f"Subtitle mismatches:   {stats['subtitle_mismatch']}")
    print(f"PASS:                  {stats['pass']}")
    print()

    content_records = stats["total"] - stats["no_hwr"] - stats["no_content"]
    if content_records > 0:
        pass_rate = stats["pass"] / content_records * 100
        print(f"Pass rate (content records): {stats['pass']}/{content_records} = {pass_rate:.1f}%")

    if issues:
        print()
        print("=== ISSUE DETAILS ===")
        for issue in issues:
            if isinstance(issue, str):
                print(f"\n  {issue}")
                continue
            print(f"\n  report_id={issue['report_id']}  type={issue['report_type']}")
            print(f"  checks: {issue['checks']}")
            if "TITLE_MISMATCH" in str(issue["checks"]):
                print(f"  title stored: {issue['title_stored']!r}")
                print(f"  title regen:  {issue['title_regen']!r}")
            if "SUBTITLE_MISMATCH" in str(issue["checks"]):
                print(f"  subtitle stored: {issue['subtitle_stored']!r}")
                print(f"  subtitle regen:  {issue['subtitle_regen']!r}")
            if "NO_START_LINE" in str(issue["checks"]) or "NO_SPEECHES" in str(issue["checks"]):
                print("  markdown snippet:")
                for line in issue["markdown_snippet"].splitlines()[:15]:
                    print(f"    {line}")


if __name__ == "__main__":
    run()
