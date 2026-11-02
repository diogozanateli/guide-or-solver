You are analyzing a software bug report to identify which files and code components to investigate.

PROBLEM STATEMENT:
{problem_statement}

REPOSITORY STRUCTURE:
{file_tree}

Task: Identify the most promising files, classes, and functions to explore for understanding this issue.

Focus on:
- Files/classes mentioned in the problem statement
- Related components that might be affected
- Common entry points and core functionality
- Test files that might reveal expected behavior

Return exactly 5-10 targets in this format:
1. target_type:file, target_name:exact_name, reasoning:why_relevant
2. target_type:class, target_name:exact_name, reasoning:why_relevant
3. target_type:function, target_name:exact_name, reasoning:why_relevant

Be specific with names—use exact file paths and class/function names from the tree. Each entry must be on a separate line and follow the exact format shown.
