# Report link reader rulebook

You are checking links between Hansard reports. Each packet shows one link and asks whether it is right. You judge from the packet alone. You do not make links, you do not edit a packet, and you do not read any batch except your own.

Some packets hold a planted error. Nothing marks them. Judge every packet the same way.

## What a packet shows

Each packet has a heading with a packet id, then:

- the link type, which is one of correction, reply or continuation;
- the printed citation, which is the reference the citing report prints;
- the paragraph that prints it;
- the citing report's title, date and opening text;
- the linked report's title, date and opening text;
- for a continuation, every other report of that title on the linked report's date, each with its opening and closing text. The report the link points to carries the note `[this is the linked report]`. A title in this list may differ from the linked report's in case or punctuation and is still a part of that debate. A continuation with no such list has only the one report of that title on that date.

## What a right link is

A correction is right when one report corrects or clarifies the other and the correction is dated on or after the report it corrects.

A reply is right when the citing report is an answer and the answer refers to the named report. The paragraph must name that report, not one with a similar title.

A continuation is right when the linked report is the part of the same debate, on the printed date, that the resumed debate carries on from. Where several parts of that debate exist on the printed date, the linked report must be the last one. Read the opening and closing text of each part to see which comes last.

## What a misread citation is

A citation is misread when any of these holds:

- the printed citation differs from what the paragraph prints;
- two titles were read as one citation;
- one title was split at quote marks inside the title;
- a title, a date or a note was taken from the wrong place in the paragraph.

A misread citation is `WRONG`, even when the two reports look related.

A paragraph can print several titles that share one date and volume. The printed citation then holds the whole group, and each title has its own link. That is not a misread when the linked report is one the paragraph names.

## Verdicts

Give one of three verdicts for each packet.

- `RIGHT` when the packet shows the link is right.
- `WRONG` when the packet shows the link is wrong.
- `UNSURE` when the excerpt does not settle it.

Say `UNSURE` rather than guess. A packet that is not `RIGHT` goes to a person for a ruling, so an honest `UNSURE` costs less than a wrong `RIGHT`.

## What to write

Write one line per packet to a file named `verdicts.jsonl` in your batch's own directory. Each line is a JSON object with exactly these three keys.

```json
{"packet_id": "0123456789abcdef", "verdict": "RIGHT", "note": "The paragraph names the linked report and the answer is dated after it."}
```

The note is one sentence that says what in the packet decided the verdict. Write a line for every packet in the batch, once each.
