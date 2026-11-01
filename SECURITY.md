# Security policy

## Report a vulnerability

Email royceinbox@hotmail.com with "Security" in the subject. Do not open a public issue for a vulnerability.

Or use GitHub's private form: [report a vulnerability](https://github.com/roycehoe/hansard-scraper/security/advisories/new).

Say which file or script is affected, the steps to reproduce it, and what an attacker could do with it.

Royce Hoe maintains this repository and reads each report himself.

## Scope

In scope:

- The code in this repository, including the daily refresh job and its Docker image.
- The scripts in `scripts/` that write to the database.

Out of scope:

- A wrong credit or missing text in the stored record. Report that on [openhansard.sg](https://openhansard.sg) with "Report an error".
- Parliament's sites, including SPRS, and the services the job runs on. Report those to their operators.
- The website that reads this database. It has its own policy in [roycehoe/hansard](https://github.com/roycehoe/hansard/blob/master/SECURITY.md).
