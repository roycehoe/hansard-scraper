# Contributing

Open an issue before you write code. A pull request that nobody discussed first may not be reviewed. A push to `master` deploys the daily refresh job, so a merged change reaches production at once.

## Reporting an error in the record

A wrong credit or missing text is a data error. Report it on [openhansard.sg](https://openhansard.sg) with "Report an error", or with the [Report an error form](https://github.com/roycehoe/hansard/issues/new?template=report-an-error.yml) on the website's repository.

## Proposing a change

1. Open an issue that says what you want to change and why. Name the report, speech or script involved.
2. Wait for Royce Hoe to reply. He decides whether the change fits the project.
3. Fork the repository, make the change, and open a pull request that links the issue.

Keep each pull request to one change. Subjects follow Conventional Commits, such as `fix: join a sentence cut by a column marker`, under 72 characters.

## Checks

CI runs `poetry run ruff check .`, `poetry run pytest` and `docker build .` on every pull request. The tests need a separate PostgreSQL database named `hansard_launch` on port 5435, on a server with the `rum` extension installed; `tests/conftest.py` refuses any other.

- A parser fix adds a golden fixture in `tests/` for the defect it closes.
- Before and after a change to parsing or linking, run `python scripts/attribution_text_share.py` and quote the three numbers it logs.
- A change that cleans data adds or updates a row in [docs/data-loss-register.md](docs/data-loss-register.md) in the same change.
- Where the record prints a value, store it as printed and put our reading in a note ([ADR 0013](docs/adr/0013-store-what-the-record-prints.md)).

## Changes to stored data

A merged pull request never changes a stored row. The daily refresh only adds rows ([docs/refresh.md](docs/refresh.md)), and the database is not published, so you cannot run a write against it. A fix to the parser reaches stored rows through a supervised write.

A write script is a dry run unless it gets `--commit`. In a supervised write, Royce runs it dry, then on a rehearsal copy of the database, then on the real one with `--commit`. Every write to the speech table ends with a figures file committed to `docs/figures/`.

If your change needs one, say so in the issue. The script can come with the pull request. Only Royce can run it, because the database is not published.
