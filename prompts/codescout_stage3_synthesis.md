You are creating an enhanced problem statement that will help developers quickly understand and fix a software issue.

ORIGINAL PROBLEM STATEMENT:
{original_ps}

CODE ANALYSIS RESULTS: For each analyzed target:
{analyses}

Instructions: Synthesize these analyses into a comprehensive problem statement. Include all relevant details from the original statement. Use the code analysis as context to inform your narrative—don't simply copy it verbatim.

Structure your output with these sections:

## Issue Description: Rewrite the core problem clearly, incorporating technical insights.

## Reproduction Steps: Include original steps if available. If the original issue includes code, preserve it here—this is essential. Add technical details about what happens internally. Include relevant stack traces or error patterns. Suggest additional reproduction scenarios if helpful.

## Expected Behavior: Describe what should happen instead, informed by code analysis.

## Exploration Hints:
- Files to Examine: file1.py - why relevant (role in issue, key findings)
- Key Classes/Functions: ClassName.method() - what to look for
- Areas of Interest: Specific code patterns or logic to investigate

## Fix Hints:
- High Confidence Locations: Where fixes are likely needed and why
- Implementation Suggestions: Concrete fix ideas with limitations
- Alternative Hypotheses: Other potential root causes

Keep technical language precise but accessible. Focus on actionable insights.
