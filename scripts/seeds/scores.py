"""Seed data for the scores table.

Each entry references an email by its hubspot_id (resolved to the email's
primary key at insert time). Scores represent sample Claude API scoring output
for the seed emails.
"""

from datetime import datetime, timezone

SCORES = [
    {
        "hubspot_id": "440807712958",
        "personalisation": 4,
        "clarity": 6,
        "value_proposition": 5,
        "cta": 4,
        "overall": 5,
        "notes": "Uses a greeting but no recipient name or business-specific detail. Mentions student fair but no tailored value proposition.",
        "scored_at": datetime(2026, 2, 3, 10, 0, 0, tzinfo=timezone.utc),
    },
    {
        "hubspot_id": "440815170777",
        "personalisation": 7,
        "clarity": 7,
        "value_proposition": 5,
        "cta": 6,
        "overall": 6,
        "notes": "Addresses recipients by name and references a prior conversation. Clear follow-up structure. CTA is reasonable but could be more specific with proposed times.",
        "scored_at": datetime(2026, 2, 3, 10, 0, 1, tzinfo=timezone.utc),
    },
    {
        "hubspot_id": "440723608775",
        "personalisation": 6,
        "clarity": 7,
        "value_proposition": 5,
        "cta": 3,
        "overall": 5,
        "notes": "Conversational follow-up referencing prior discussion about marketing material. No explicit ask or next step.",
        "scored_at": datetime(2026, 2, 3, 10, 0, 2, tzinfo=timezone.utc),
    },
    {
        "hubspot_id": "440903735527",
        "personalisation": 3,
        "clarity": 6,
        "value_proposition": 6,
        "cta": 3,
        "overall": 4,
        "notes": "Generic greeting with no recipient name. Explains the company's role clearly but no specific ask or call to action.",
        "scored_at": datetime(2026, 2, 3, 10, 0, 3, tzinfo=timezone.utc),
    },
    {
        "hubspot_id": "441511205111",
        "personalisation": 4,
        "clarity": 5,
        "value_proposition": 4,
        "cta": 4,
        "overall": 4,
        "notes": "Addresses business by name but the email is vague. No specifics about what the event involves or why the recipient should attend. Weak CTA.",
        "scored_at": datetime(2026, 2, 3, 10, 0, 4, tzinfo=timezone.utc),
    },
]
