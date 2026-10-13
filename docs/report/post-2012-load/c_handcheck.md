RESULT: 28 of 30 right
00077571-WA.00077603-WA_9#hansardContent43a675dd-5000-42da-9fd5-40978d79310f# | right | sprs2 header table kept, speakers bold, text in order
00076464-WA.00076467-WA_8#hansardContent43a675dd-5000-42da-9fd5-40978d79310f# | right | subtitle survives as H2, text in order
00076980-WA.00076983-WA_11#id-5920d3c9-55bc-4e9e-b5b4-caf3710c57e8# | right | note: italic split renders as '_h_ _alal_' (stray space inside halal); text intact
00077461-WA.00077424-WA_4#id-795a28f5-d5d8-447e-9276-4752c6440195# | right | short bill intro, complete
written-answer-na-1058# | right | page marker dropped, text and bold labels intact
written-answer-2025# | right | right
oral-answer-212# | right | page marker dropped, supplementary labels bold
bill-111# | right | proc text markers removed, time as heading
bill-intro-68# | right | proc text markers and brackets removed, text complete
motion-416# | right | '[(proc text) ...]' gone, S&CC intact
budget-165# | right | headings kept as italic H6; bracketed [12 March 2013] and [Mr Cedric Foo Chee Keng] are source text
matter-adj-407# | right | adjournment headings and bold labels intact
ministerial-statement-172# | right | right
written-answer-na-4356# | right | nbsp became plain spaces, no glue
written-answer-5528# | wrong | footnote superscripts glued to numbers: '248<sup>4</sup>' became '2484', '473<sup>5</sup>' became '4735', '8.3<sup>6</sup>' became '8.36', 'days<sup>1</sup>' became 'days1'; reads as wrong figures
oral-answer-1713# | right | right
motion-936# | right | short adjournment, proc text marker removed, italic time kept
bill-intro-263# | right | right
bill-197# | right | title has trailing space in DB (harmless)
budget-705# | right | right
president-address-258# | wrong | speaker label glued: source '<strong>The </strong><strong>Deputy...' became '**The****Deputy Prime Minister...**' so the space after 'The' is lost and the bold markers are malformed
matter-adj-1275# | right | right
written-answer-17489# | right | right
written-answer-na-7852# | right | empty paragraph left as a blank line, nit
oral-answer-2652# | right | right
motion-2478# | right | note: title 'Adjournment Motion' is generic while the topic heading is 'Reimagining the Future of Education'; text intact
bill-701# | right | right
budget-2091# | right | note: chairman line is rendered as an H6 heading containing the bold label; label still bold, text intact
bill-intro-567# | right | right
matter-adj-1680# | right | right

Defect patterns:
1. Superscript footnote markers (sprs3 <sup>n</sup>) are flattened into the preceding digits, which changes numbers (row written-answer-5528#). Any sprs3 row with footnotes after a figure is at risk.
2. Adjacent <strong> runs split by a trailing space inside the first tag are joined as '**A****B**' with the space lost (row president-address-258#). The label is no longer a clean bold label and the words glue.
Nits only: italic runs split mid-word give '_h_ _alal_' (sprs2 row 00076980-WA...); generic title on a motion row; label inside H6 heading.
No proc text markers, base64, missing starts or foreign text found in any of the 30. Parliament, date and type fit the content in all 30.
