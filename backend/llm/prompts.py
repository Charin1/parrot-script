MEETING_SUMMARY_PROMPT = """
You are an expert meeting analyst.

Analyze the following transcript and return ONLY valid JSON formatted strictly like this, and absolutely nothing else:

{
  "summary": "2-3 sentence high-level overview of the meeting.",
  "action_items": [
    "Alice will schedule a follow-up meeting with Bob.",
    "Charlie to draft the XYZ report by Friday."
  ],
  "decisions": [
    "We will migrate to PostgreSQL next month.",
    "Budget approved for the Q4 marketing campaign."
  ]
}

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

Return ONLY valid JSON formatted strictly like this, and absolutely nothing else:

{
  "summary": "2-3 sentence high-level overview of the entire meeting.",
  "action_items": [
    "Alice will schedule a follow-up meeting with Bob.",
    "Charlie to draft the XYZ report by Friday."
  ],
  "decisions": [
    "We will migrate to PostgreSQL next month.",
    "Budget approved for the Q4 marketing campaign."
  ]
}
"""
