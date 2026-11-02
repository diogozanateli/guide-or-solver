You are analyzing code content to understand how it relates to a specific bug report. Your analysis will directly feed into an augmented problem statement.

ORIGINAL PROBLEM:
{problem_statement}

CODE CONTENT:
{content}

TARGET INFO: {target_type} - {target_name}

Provide analysis in the following format:

RELEVANCE: X/10

ROLE_IN_ISSUE:
Describe how this code relates to the reported issue. What is its role in causing or manifesting the bug?

FIX_LOCATION_HINTS:
Identify specific locations where fixes might be needed (line numbers, methods, conditions). What type of changes might be required (validation, error handling, logic fixes)?

EXPLORATION_INSIGHTS:
Surface key technical details that help understand the issue—algorithms, data flow, dependencies, code patterns, or architectural decisions relevant to the bug. Note test scenarios or edge cases this code suggests should be examined.

ALTERNATIVE_HYPOTHESES:
Consider alternative explanations for the bug based on this code. What related components might also be involved? What different root causes does this analysis suggest?

Note: Focus on insights that will help create actionable exploration hints and fix suggestions. If relevance < 4, keep all sections brief but still provide analysis.
