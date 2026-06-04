Goal: Create a table for speaker names and link them to speeches

Problem: In speeches, some speaker names are not MPs
Problem: In speeches, some speaker names are outright wrong

Solution: Create a loop to clean data, similar to the OCR cleaning

Method: Look at all unique names of all speakers in speeches table
Method: Attempt to match them to MP names with OCR utils
Method: Eliminate those that successfully parse
Method: For the remaining names, do a heuristic check to see if they are indeed names
Method: Count the number of times wrong names appear in all speeches as we want to start with the easy to fix ones
Method: Come up with a hypothesis why the name is wrong and fix the speech/speaker logic
Method: Test hypothesis
Method: (optional) Run regression on the speech/speaker logic to ensure that we still hold speech/speaker 95% success rate
Method: Start again

This loop pipeline should miror the other loop pipelines
