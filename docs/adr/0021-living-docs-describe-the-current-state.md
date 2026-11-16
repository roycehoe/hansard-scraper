# 0021. Living documents describe the current state

Status: accepted, 16 November 2026.

Context. The repo's documents fall into two kinds. Living documents (`CLAUDE.md`, `STYLE.md`, `README.md`, `CONTRIBUTING.md` and the reference docs under `docs/`, such as `vision.md`, `data-loss-register.md` and `refresh.md`) are kept up to date and read as instructions or reference. Dated records (the reports in `docs/report/`, these ADRs and the refine-loop logs) say what was known on their date. Over time the living documents filled with history: who ruled, on which day, and what each write changed in turn. A reader looking for the rule had to read past the story of how it came about, and an agent loading `CLAUDE.md` paid for that history every session.

Decision. A living document says how things stand now. It states a rule as a rule, names no person, and gives no date for when someone decided it. It keeps dates that describe the record or the data, such as "sittings before 10 September 2012", and dated file names such as `docs/figures/2026-11-02-write13.txt`. Where a document must say that a person decided, as the data loss register's Decided column does, it says "the maintainers". History goes to git, to `docs/report/figures-history.md` and to the dated records, which keep their dates. The writing rules are in `docs/WRITING.md`.

Why. A rule reads the same whether it was set last week or last year, and the date and the name add nothing a reader acts on. Keeping them made each rule longer, and the documents went stale in a new way: a sentence such as "last recalibrated after write #13" is wrong the day after the next write. Git already records who changed what and when, and `git log -S` finds the commit that brought in any sentence.

Alternatives.

- Keep dates and names in living documents, as before. Rejected, because the history crowded out the rules.
- Move history into a changelog file. Rejected, because git and the dated records already hold it, and a second copy would drift.
