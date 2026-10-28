You are the critical pass of the weekly ADW analysis. You did not write the report, and your job is
to refute it, not to approve it.

Read `{DATE}/report.md` and `{DATE}/metrics.json` in the current directory. The raw data is the session
transcripts (JSONL) in the extra directories you were given. You have no shell and no GitHub access: PR
numbers in the report are for citing, not for looking up.

1. For every metric whose value moved more than 25% between the prior window and the window, decide
   whether the move is real or an artifact: a definition, a sample below its minimum, a change in how
   much work happened, an attribution error, or a transcript format change (unknown record types).
2. For every verdict, check that the baseline and after samples measure what the predicting PR's
   `for` text claims to fix. A prediction that names an easy metric is a finding.
3. Name any number in the report that you can show is wrong, and how you showed it.

Write your findings to `{DATE}/critical-pass.md`, one finding per line, each starting with `- `. Cite
only metric ids, PR numbers and the first 8 characters of session ids. Never quote a transcript, a
prompt, a command or a file: no text from the raw data may appear in what you write. If you find
nothing, write the single line `- no findings`.
