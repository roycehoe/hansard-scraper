# Subagent 1

I would like you to spin up a subagent that looks at the code and validates that everything in my @docs/ aligns with what the code claims it does. Ensure that variable names/database row names are aligned with the code. If they are not aligned, the code is the source of truth; update the docs accordingly.

After you are done, commit your changes (grouped by concerns) and push

# Subagent 2
I would like you to review my vision.md file.

My project has a vision that may not be captured accurately in the vision.md file. Here's what I want this project to do.

Look at my @database/sitting.py. It contains a field called markdown_content.
Look at my @database/report.py. It contains a field called markdown_content.

My goal is to be able to reconstruct the markdown_content exactly as how it appears, but with speaker names properly indexed and normalized. 

How this would look is, should I do something like this in pseudocode:

```python
report = get_report(1)
for line in report.markdown_content.splitlines():
    print(line)

speeches = get_speech_by_report_id(report.id)
    .sort_by_ordinal(
    sort_type="smallest_to_largest"
)
for speech in speeches:
    print(f"{speaker}: {transcript}")
```

The printed content would be virtually identical.

The idea is, as a researcher, with this database, I can search reports by speaker names.

Does my current application achieve this goal? If not, what is the gap? Do not implement anything. Report your findings and, if there is a gap, propose a plan to close it.


# Subagent 3
I would like you to look at all my markdown files in my repo. Some of them may be updated, containing execution plans that have already been executed (these were previous plans that were written to be executed in future, but after they have been executed, they were unwittingly not deleted). Your goal is to identify these files and create a summary table of them.

To determine whether a plan has already been executed, use the following heuristics:
- **One-time plans** (files in `plans/` or docs describing a specific implementation task): treat as executed if the files, functions, or DB schema they describe exist in the current codebase.
- **Living TODO/improvement documents**: treat as stale only if every listed item has been implemented.

For each candidate file, apply /think-style reasoning: produce a pros/cons table and a clear delete/keep recommendation. Do not delete anything — present your findings and stop.


# Subagent 4
Please look at my STYLE.md and replace the code examples (all code blocks) with equivalent examples drawn from my codebase. Do not change any prose, rules, or section structure — only the code snippets. Leave rules unchanged even if a codebase example does not exist for them.
