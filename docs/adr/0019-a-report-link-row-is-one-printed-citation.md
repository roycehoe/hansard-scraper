# 0019. A report link row is one printed citation

Status: accepted, 9 November 2026. The shape of the table was settled at the two planning gates of the links build, by an independent reviewer while Royce was away. The number stays NNNN until the features that are built together land and the ADRs are numbered in order. The rule that a link comes only from a fixed rule that finds one target is hansard ADR 0011.

Context. A report prints references to other reports. A correction says which statement it corrects, an answer says which report it replies to, and a debate resumed on a later day says which sitting it carries on from. The project turns these references into links between reports. A reader of the table sees a source report, a target report and a type, and cannot tell from those columns why the same two reports can appear in two rows. `plans/` is not committed, so nothing else in the repository says why.

Decision. A `report_link` row is one printed citation, stored on the report that prints it. It holds the link type, the rule that found the one target, the citation as the record prints it, and the two report ids. The table is unique on source report, target report and link type. When a correction pair is printed from both sides, each report cites the other, so the pair is two rows, one for each printing. The API returns such a pair once and builds the two-way display itself, with the relations `corrects`, `corrected_by`, `refers_to` and `continues`. A rule links only when it finds exactly one target. Zero or several targets give no link, and the plan records the reason.

Why. The project stores what the record prints (ADR 0013). A mirror row for the side that prints nothing would hold a citation nobody printed, and the row could not say which report carries the words. One row per pair would drop the direction of the printing. Some correction pairs are printed only on the corrected side, so a table that stored corrections from the correcting side alone would lose them. Keeping the printing in the row also lets a reader check any link against the report text, and lets the daily run tell a stale row from a current one by comparing the rule and the citation.

Consequences.

- A count of rows is a count of printings. A count of linked pairs is a query in the API, not a count of this table.
- The daily run inserts rows and never deletes, because the refresh role has no DELETE grant. A row that no longer matches the record is reported as stale, and `python -m scripts.apply_report_links --commit` rewrites the table.
- A write that adds, rewrites or deletes speech rows of any report ends with that script, since a citation lives in a speech row.

Alternatives.

- Store each pair once, with the correcting report as the source. This loses the pairs printed only on the corrected side and hides which report prints the citation.
- Store each pair twice, once for each direction, whether or not both sides print it. This adds rows the record does not print.
