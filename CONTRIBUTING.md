# Contributing

Open an issue before you write code. A pull request that nobody discussed first may not be reviewed. A push to `master` deploys the daily refresh job, so a merged change reaches production at once.

## Reporting an error in the record

A wrong credit or missing text is a data error. Report it on [openhansard.sg](https://openhansard.sg) with "Report an error", or with the [Report an error form](https://github.com/roycehoe/hansard/issues/new?template=report-an-error.yml) on the website's repository.

## Proposing a change

To submit a change:

1. Open an issue that says what you want to change and why. Name the report, speech, or script involved.
2. Wait for the maintainers to reply. The maintainers decide whether the change fits the project.
3. Fork the repository, make the change, and open a pull request that links the issue.

Keep each pull request to one change. Write subjects that follow Conventional Commits, such as `fix: join a sentence cut by a column marker`, under 72 characters.

## Checks

CI runs `poetry run ruff check .`, `poetry run ruff format --check .`, `poetry run basedpyright`, `poetry run pytest`, and `docker build .` on every pull request. The tests need a separate PostgreSQL database named `hansard_launch` on port 5435, on a server with the `rum` extension installed; `tests/conftest.py` refuses any other.

Follow four rules when changing code or data:

- Add a golden fixture (a trimmed source HTML excerpt and the speech rows the parser must produce) in `tests/` for the defect a parser fix closes.
- Before and after a change to parsing or linking, run `python scripts/attribution_text_share.py` and quote the three numbers it logs.
- For a change that cleans data, add or update a row in [docs/data-loss-register.md](docs/data-loss-register.md) in the same change.
- Where the record prints a value, store it as printed and put the project's reading in a note ([ADR 0013](docs/adr/0013-store-what-the-record-prints.md)).

## Changes to stored data

A merged pull request never changes a stored row. The daily refresh adds rows and widens the bounds of the seat history ([docs/refresh.md](docs/refresh.md)), and the database is not published, so you cannot run a write against it. A fix to the parser reaches stored rows through a supervised write.

A write script is a dry run unless it gets `--commit`. In a supervised write, the maintainers run it dry, then on a rehearsal copy of the database, then on the real one with `--commit`. Every write to the speech table ends with a figures file committed to `docs/figures/`.

If your change needs a supervised write, say so in the issue. The script can come with the pull request. Only the maintainers can run it, because the database is not published.
