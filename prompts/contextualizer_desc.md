You are analysing an issue in the repository located in the current working
directory. You may run read-only bash commands (ls, cat, grep, find, python -c).
Do NOT edit files and do NOT write any implementation code.

## Issue

{issue}

## Output

When your analysis is complete, run `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`
and, in the same message, return ONLY a JSON object with this schema:

```json
{
  "problem": "what is wrong, in plain language",
  "root_cause": "most likely cause",
  "files": ["path/to/file.py"],
  "functions": ["module.Class.method"],
  "change_description": "what must change, in prose, without code"
}
```

The guidance must not contain code snippets, diffs or pseudo-code.
