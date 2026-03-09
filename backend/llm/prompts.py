MEETING_SUMMARY_PROMPT = """
You are an expert meeting analyst.

Analyze the following transcript and return ONLY valid markdown with these exact sections:

## Summary
(2-3 sentence high-level overview)

## Key Discussion Points
- point 1

## Decisions Made
- decision 1 (or "None identified")

## Action Items
| Assignee | Task | Notes |
|----------|------|-------|
| Name | Description | context |

## Risks & Blockers
- risk 1 (or "None identified")

## Next Steps
- step 1

TRANSCRIPT:
{transcript}
"""

PARTIAL_SUMMARY_PROMPT = """
Summarize this portion of a meeting transcript in 3-5 bullet points.
Focus on key topics, decisions, and action items.

TRANSCRIPT PORTION:
{transcript}
"""

COMBINE_SUMMARIES_PROMPT = """
You are combining multiple partial meeting summaries into a final structured summary.

PARTIAL SUMMARIES:
{summaries}

Return ONLY valid markdown with these sections:
## Summary
## Key Discussion Points
## Decisions Made
## Action Items (table format)
## Risks & Blockers
## Next Steps
"""
