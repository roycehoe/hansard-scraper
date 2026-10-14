# Post-September 2012 report text, 13 October 2026

**Status, 14 October 2026: closed.** The fetcher now picks the id and the response field by system, and the production load ran. 16,123 newer-system reports were filled with text, and 3,880 skipped search hits were inserted (3,769 newer-system, 111 older-system Parliament 12 hits before 10 September 2012). The database now holds 41,809 distinct records, 41,678 with text. The 131 without text were 106 `atbp` records (the newer system gives them no topic text) and 25 others, 11 of them newer-system ids that returned no text. A later recovery (see [post-2012-load.md](post-2012-load.md)) filled 3 of the 11 by retrying and added 2 re-prefixed hits with text, leaving 6 that the API answers with HTTP 400 on every attempt. The sections below describe the gap as found on 13 October 2026 and are kept as written.

Read-only. No DB write, no code edit. DB claims name the query, which ran inside `BEGIN READ ONLY ... ROLLBACK`. API claims give the exact request so you can rerun it.

## 1. What the database holds

Every report from 10 September 2012 onward has no text.

- `select max(sitting_date) from report where content is not null and content<>''` returns 2012-08-13.
- `select min(sitting_date) from report where parliament_number=12 and content is null` returns 2012-09-10.
- Before that date, one record lacks text: `select count(*) from report where content is null and sitting_date < '2012-01-01'` returns 1.
- In `hansardwebsiteresponse`, content is present on exactly the rows that have an `html_file_name`. P12 has 936 of each out of 4,014. P13 has 0 of 5,593 and P14 has 0 of 11,303.

Deduplicated by `report_id`, 16,222 records have no text. That's 2,595 in P12, 4,568 in P13 and 9,059 in P14.

Sitting HTML has the same gap. `html_full_content` is present for 67 of 270 sittings in the 2010s and 0 of 183 in the 2020s.

## 2. How SPRS splits the record

SPRS runs two systems and switches between them on 10 September 2012. The front-end bundle (`https://sprs.parl.gov.sg/search/main.6c50b646860a7eb9.js`) has this line:

```js
this.sprs2Date=new Date("2012/09/10"),this.selectedDate>=this.sprs2Date?localStorage.setItem("silo","sprs3"):localStorage.setItem("silo","sprs2")
```

| | sprs2 (before 10 Sep 2012) | sprs3 (from 10 Sep 2012) |
|---|---|---|
| Topic page route | `#/topic` | `#/sprs3topic?reportid=...` (lazy chunk 390) |
| Sitting page route | `#/report` | `#/fullreport` (lazy chunk 371) |
| `reportId` shape | `00077544-WA.00077538-WA_3#speaker#` | `oral-answer-3851#` |
| `htmlFileName` in search hit | present, e.g. `002_20111010_S0012_T0001` | null |
| `reportVersion` | sprs2 | sprs3 |

Both silos call the same two endpoints. The site sends the ID as a JSON body: `authHttp.post(getHansardTopicURL, {id: X})` and `authHttp.post(getHansardReportURL, {sittingDate: X})`.

## 3. Requests that work today

sprs3 topic. Send `reportId` with the trailing `#` removed. The text is in `resultHTML.content`, not `htmlContent`.

```bash
curl -s -X POST https://sprs.parl.gov.sg/search/getHansardTopic \
  -H 'Content-Type: application/json' -d '{"id":"oral-answer-3851"}'
```

This returns HTTP 200, 13,361 bytes. The top-level keys are `resultData`, `resultHTML`, `type`, `sittingDate` and `questionCount`. `resultHTML.content` holds 12,040 characters of HTML that starts `<p>3 <strong>Ms Carrie Tan</strong> asked&nbsp;the Minister for National Development`. `resultHTML.htmlContent` and `resultHTML.htmlFileName` are null. With the `#` left in (`{"id":"oral-answer-3851#"}`), the API returns HTTP 400. My guess is the site never sends the `#` because the hash router treats it as a fragment. I haven't verified that.

At the boundary, `{"id":"written-answer-934"}` (sitting 10-9-2012) returns `reportVersion` sprs3 and `content` with 2,725 characters.

sprs2 topic. Send `htmlFileName`. The text is in `htmlContent`.

```bash
curl -s -X POST https://sprs.parl.gov.sg/search/getHansardTopic \
  -H 'Content-Type: application/json' -d '{"id":"002_20111010_S0012_T0001"}'
```

This returns `htmlContent` with 4,392 characters. Sending the sprs2 `reportId` instead (`00075323-ZZ.00074933-ZZ_2##`) returns HTTP 400.

Sitting report. Both formats answer to a JSON body:

```bash
curl -s -X POST https://sprs.parl.gov.sg/search/getHansardReport \
  -H 'Content-Type: application/json' -d '{"sittingDate":"06-03-2018"}'
```

The 2018 response has `metadata`, `attendanceList`, `ptbaList`, `a2bList` and `takesSectionVOList`, but no `htmlFullContent`. `takesSectionVOList` has 10 sections, and each carries `title`, `sectionType` and full `content` HTML. The first is "Suspension of Standing Order 91", starting `<p><strong>The Leader of the House (Ms Grace Fu Hai Yien)</strong>:`. The 1968 request (`{"sittingDate":"16-12-1968"}`) returns the old flat format with `htmlFullContent` at 287,701 characters.

## 4. Requests that fail today

The current gateways put the ID in the query string. For every record I tried, old or new, that form now returns `{"errorCode":500,"description":"Unable to process the request. Please try after sometime."}`.

- `gateway/hansard_topic.py` sends `POST .../getHansardTopic/?id=<id>`. It failed for `oral-answer-3851#`, `00075323-ZZ.00074933-ZZ_2##` and `002_20111010_S0012_T0001`.
- `gateway/hansard_report.py` sends `POST .../getHansardReport/?sittingDate=<date>`. It failed for 06-03-2018 and 16-12-1968.

I sent the JSON-body requests in section 3 within the same few minutes and they succeeded, so the 500 comes from the request format and not an outage. Pre-2012 text is already stored, so a refetch of any era would fail with today's gateways.

## 5. Why the gap exists

The pipeline asks for the wrong thing on sprs3 records. `populate/hansard_responses.py` calls the topic API with `result.html_file_name or result.report_id`, and then reads `response.get("htmlContent")`. For sprs3 records:

- `html_file_name` is null, so the call falls back to `report_id`, which still has the trailing `#`.
- The text is in `resultHTML.content`, so even a successful response would yield `htmlContent` None.

Either one is enough to store `content = None` without an error. The fetch logs a warning only when the gateway raises.

## 6. Was post-2012 excluded on purpose?

It was excluded in code from the start, but no written decision exists, and later docs say the opposite.

- `d505062` ("chore: successfully load all parliament html into database", 26 Aug 2025) fetched topic HTML only for `Report.sitting_date < datetime(2012, 9, 10)`. That is the SPRS silo date to the day, so the cutoff was chosen knowingly.
- `ece9787` (26 Aug 2025) narrowed the same fetch to rows that have an `html_file_name`, which also leaves out sprs3.
- `1fe6602` (26 Aug 2025) and `49e3e66` (28 Aug 2025) applied the same cutoff to parsing (`select(Report).where(Report.sitting_date < datetime(2012, 9, 10))`).
- Later refactors (`11b3cc1`, `26aac3e`, `4154ca7`, `afcf9af`) removed the cutoff from fetch and parse. The fetch kept the sprs2-only request shape, so sprs3 records came back empty.
- No cutoff is left in code. The diagnostic sampler that used 10 Sep 2012, `get_strata_sample`, was removed as unreferenced in the style sweep.
- No commit message, ADR, plan or doc gives a reason. `git log --grep` for 2012, sprs2, sprs3 and silo finds nothing.
- `docs/vision.md` scopes the project "from the colonial Legislative Assembly through the present". The README says P12's "fetch is incomplete" and that "speeches exist only for Parliaments 0 to 12", which describes the gap but not its cause.

## 7. What a fix would involve (not started)

- Change both gateways to send a JSON body, as the site does.
- For sprs3 topics, send `report_id.rstrip("#")` and read `resultHTML.content`.
- Decide where sprs3 text goes in the raw table. `htmlContent` is null in sprs3 responses, so storing `resultHTML.content` in `content` is a transformation the raw-first rule needs to allow.
- Check the speech parser against sprs3 HTML before trusting any speech counts. The sample uses inline `<strong>Name</strong>` inside numbered question paragraphs. `docs/parsing.md` covers P12 format changes up to 2012, not this markup.
- Optional cross-check: `takesSectionVOList[].content` from the sitting report carries the same debate text per section. The `sitting.sections` column is null in all 1,719 rows (see `plans/duplicate-reports.md`), even though the API returns sections for sprs3 dates.

Sample size: I probed 2 sprs3 topics (P14 8-4-2025 and P12 10-9-2012), 1 sprs2 topic, and 2 sitting dates. I did not test a long debate or a bill reading in sprs3.
