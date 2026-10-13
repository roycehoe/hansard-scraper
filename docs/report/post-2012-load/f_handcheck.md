RESULT: 30 of 30 attendance right, 5 of 5 sittings right

Attendance (row index, id, stored name, verdict)
0 id 102827 Raymond Lim Siang Keat, absent, East Coast, 15-11-2012: right, matches API entry.
1 id 111723 Chia Shi-Lu, absent, Tanjong Pagar: right, Dr removed.
2 id 121005 Lily Neo, absent, Tanjong Pagar: right, Dr removed.
3 id 123003 Masagos Zulkifli Bin Masagos Mohamad, absent, Tampines: right, API "Masagos Zulkifli B M M" mapped to the required form, portfolio dropped.
4 id 133678 Fatimah Lateef, absent, Marine Parade: right, Assoc Prof removed.
5 id 129803 Foo Mee Har, present, West Coast: right.
6 id 129002 Thomas Chua Kee Seng, present, Nominated Member: right.
7 id 123157 Lim Biow Chuan, present, Mountbatten: right (his own entry, not the Speaker line).
8 id 112603 Yee Jenn Jong, present, Non-Constituency Member: right.
9 id 108665 Liang Eng Hwa, present, Holland-Bukit Timah: right, confirmed in the full cached list.
10 id 114312 Douglas Foo, absent, Nominated Member: right.
11 id 121095 Fatimah Lateef, absent, Marine Parade, 2017: right.
12 id 124112 Sun Xueling, absent, Pasir Ris-Punggol: right, long portfolio dropped.
13 id 129183 Tharman Shanmugaratnam, absent, Jurong: right.
14 id 107916 K Shanmugam, absent, Nee Soon: right, name kept as the API writes it.
15 id 120036 Indranee Rajah, present, Tanjong Pagar: right.
16 id 133954 Tan Wu Meng, present, Jurong, 3-3-2020: right, confirmed in the full list (Dr Tan Wu Meng, Jurong, true).
17 id 126600 Darryl David, present, Ang Mo Kio, 2020: right.
18 id 96967 Ong Teng Koon, present, Marsiling-Yew Tee: right, confirmed in the full list.
19 id 125256 Ng Chee Meng, present, Pasir Ris-Punggol: right, acting-minister text dropped.
20 id 104725 Koh Lian Pin, absent, Nominated Member: right, Prof removed.
21 id 129981 Ng Eng Hen, absent, Bishan-Toa Payoh: right.
22 id 134278 Lim Biow Chuan, absent, Mountbatten, 2023: right.
23 id 129979 Lee Hsien Loong, absent, Ang Mo Kio: right.
24 id 134381 Mohd Fahmi Bin Aliman, absent, Marine Parade: right, canonical long form of API "Mohd Fahmi Aliman".
25 id 111534 Cheryl Chan Wei Ling, present, East Coast: right, Miss removed.
26 id 122729 Janil Puthucheary, present, Pasir Ris-Punggol: right.
27 id 123920 Darryl David, present, Ang Mo Kio, 2021: right.
28 id 128034 Rachel Ong, present, West Coast: right, confirmed in the full list (Miss Rachel Ong, West Coast).
29 id 106537 Chua Kheng Wee Louis, present, Sengkang: right.

Sittings
0 id 6709 (8-7-2019): right. All metadata fields equal the API. Lists: vernaculars 4 and a2b 4 and annexures 0 match exactly; attendance, ptba and sections are cut at 1,500 chars here, their stored text matches the start of the API lists (100, 167, 109 items), so counts could not be seen in full.
1 id 6470 (18-8-2015): right. Metadata equal. ptba 1, vernaculars 5, a2b 8, annexures 0 match; attendance (98) and sections (33) are cut, prefix matches.
2 id 6485 (21-3-2018): right. Metadata equal. ptba 2, vernaculars 4, a2b 0, annexures 0 match; attendance (100) and sections (8) cut, prefix matches.
3 id 6461 (10-3-2015): right. Metadata equal. ptba 9, a2b 0, annexures 0 match; vernaculars (7), attendance (99), sections (10) cut, prefix matches.
4 id 7002 (18-5-2018): right. Metadata equal. ptba 10, vernaculars 5, a2b 0, annexures 0 match; attendance (100) and sections (32) cut, prefix matches.
online_pdf_file_name is null on all five, which the rules allow.

Defect pattern
None found. Limit of the check: the cut list columns (attendance_list and sections on all five, plus ptba_list on sitting 0 and vernaculars on sitting 3) could only be checked by their opening text, not by item count. Sections text uses – escapes where the API has the literal dash, which is normal JSON serialisation and not a defect.
