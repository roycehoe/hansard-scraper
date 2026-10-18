# 0004. Link URLs dropped from report markdown

Status: accepted, 15 October 2026. Revisit after the speech fidelity loop.

Context. html2text rendered each link as `[text](url)`, so report markdown and speech rows carried download URLs inside the speech text: vernacular-speech PDFs, annexes and footnote anchors. The raw HTML keeps every URL.

Decision. `get_cleaned_report_markdown` sets `converter.ignore_links = True`, so report markdown keeps the link text and drops the URL (`bbf52de`). Sittings keep their links. The Committee of Supply note rule matches the plain-text form. A row that held only a link has no text left and is deleted.

Consequences. The URL of every link in a report is gone from `Report.markdown_content` and from the speech rows built from it. The dry run counted 1,759 reports and 4,068 rows, and 3 rows deleted because they held only a link. The combined write of 15 October 2026 applied it. The words of a vernacular-speech pointer stay ("For vernacular speech, please refer to Appendix A") and its target does not, so a reader of the speech table cannot reach the PDF from the row. The URLs come back by re-running the parser on `HansardWebsiteResponse.content`, which holds them unchanged.

Revisit. The user's recommendation is to keep the URLs in a separate column after the loop, so the vernacular-speech pointer is not lost. That needs a migration and a change to the parser's output, and is not built.

Alternatives. Keep the links in the text, as before `bbf52de`: speech rows then carry URLs. Store the URLs in a column now: not built. The user's recommendation puts it after the loop. Drop links from sittings too: not done, and no reason is recorded.
