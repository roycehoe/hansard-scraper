RESULT: 30 of 30 right
written-answer-1230#: right, asker line and answer intro kept; the base64 table image is dropped, no image data in markdown (markdown is short because the rest of the HTML is the image)
written-answer-na-2143#: right, asker line, answer and mid-sentence page break join all intact
oral-answer-786#: right, asker line (with the span split) and bold minister label intact; page marker removed cleanly
motion-115#: right, proc text brackets removed, nbsp became a space, adjournment line intact
budget-200#: right, proc text lines kept as plain text without markers, bold speaker label intact, page break joined
bill-56#: right, proc text removed, time heading kept as heading, speaker label bold
bill-intro-93#: right, both proc text paragraphs kept, markers and brackets gone, page marker removed
president-address-343#: right, speech text matches in order across head, speaker label bold, page break joined
matter-adj-75#: right, headings, bold labels and text intact; nit: italic runs around the Mandarin note and vernacular link render as '_:_[_Please refer to[ Vernacular Speech](...)_' but the words are all there
ministerial-statement-482#: right, bold PM label and paragraphs match
written-answer-4960#: right, asker line and answer intact, nbsp gave normal spaces, no glued words
written-answer-na-2992#: right, asker line and answer intact
oral-answer-1504#: right, two question lines (7 and 8) kept, all bold labels survive, nbsp handled
motion-980#: right, single bold Deputy Speaker line intact, zero-width char dropped
bill-247#: right, proc text removed, time heading, bold label and text match
budget-857#: right, chairman heading with bold, italic subheading, bold member label and text match
bill-intro-13#: right, both proc text paragraphs kept without markers
president-address-9#: right, bold minister label and paragraphs match; president-address type fits a ministry segment of the address debate
ministerial-statement-1404#: right, proc text line plain, Deputy Speaker label bold, time heading, text matches with nbsp as spaces
speaker-686#: right, speaker label bold, NMP names listed in order, closing paragraphs intact
written-answer-6613#: right, asker line and answer intact
written-answer-na-10771#: right, asker line and answer intact
oral-answer-2979#: right, asker line, long bold label and answer match
motion-1447#: right, minister label bold, motion text and both resolved/put lines kept
bill-581#: right, proc text plain, labels bold, time heading, text matches (title has a trailing space only)
budget-1832#: right, proc text plain, labels bold, time heading, text matches
bill-intro-430#: right, both proc text paragraphs kept, span split joined cleanly
matter-adj-1932#: right, headings, bold labels, text match; nbsp handled with no glued words
president-address-2137#: right, bold minister label and paragraphs match
written-statement-2402#: right, both statement versions kept, bold labels survive, bold 'and roads' runs kept; nit: italic/link run renders as '_Please refer to "__Title_ _"' with stray underscores and space, text intact

Defect patterns: none that lose or add text. No glued words, no (proc text) markers, no base64 data, no stray bracket pairs, no missing asker lines or numbered paragraphs, no foreign text in the 4,000-character heads.
Nits only: italic and link runs inside bracketed cross-reference notes (rows matter-adj-75# and written-statement-2402#) leave stray underscores; speaker labels render as '**Name** :' with a space before the colon (consistent across all rows); Page: markers are dropped.
Limit: written-answer-1230# has 39,548 HTML characters, almost all a base64 table image, and only the first 5,000 were available, so text after the image could not be checked.
