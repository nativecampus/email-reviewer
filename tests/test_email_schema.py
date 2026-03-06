from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.email import EmailResponse
from app.schemas.score import ScoreCreate, ScoringResult


VALID_SCORING_RESULT = {
    "personalisation": 5,
    "clarity": 5,
    "value_proposition": 5,
    "cta": 5,
    "notes": "Solid email.",
}

SCORE_FIELDS = [
    "personalisation",
    "clarity",
    "value_proposition",
    "cta",
]


class TestScoringResultRange:
    def test_rejects_personalisation_below_range(self):
        data = {**VALID_SCORING_RESULT, "personalisation": 0}
        with pytest.raises(ValidationError):
            ScoringResult(**data)

    def test_rejects_personalisation_above_range(self):
        data = {**VALID_SCORING_RESULT, "personalisation": 11}
        with pytest.raises(ValidationError):
            ScoringResult(**data)

    def test_accepts_boundary_low(self):
        data = {**VALID_SCORING_RESULT, "personalisation": 1}
        result = ScoringResult(**data)
        assert result.personalisation == 1

    def test_accepts_boundary_high(self):
        data = {**VALID_SCORING_RESULT, "personalisation": 10}
        result = ScoringResult(**data)
        assert result.personalisation == 10

    def test_accepts_mid_range(self):
        result = ScoringResult(**VALID_SCORING_RESULT)
        assert result.personalisation == 5


class TestScoringResultRequired:
    @pytest.mark.parametrize("field", SCORE_FIELDS + ["notes"])
    def test_missing_field_raises(self, field):
        data = {**VALID_SCORING_RESULT}
        del data[field]
        with pytest.raises(ValidationError):
            ScoringResult(**data)


class TestScoreCreate:
    def test_rejects_score_below_range(self):
        with pytest.raises(ValidationError):
            ScoreCreate(
                email_id=1,
                personalisation=0,
                clarity=5,
                value_proposition=5,
                cta=5,
                overall=5,
                notes="Test",
            )

    def test_accepts_valid_range(self):
        sc = ScoreCreate(
            email_id=1,
            personalisation=1,
            clarity=10,
            value_proposition=5,
            cta=5,
            overall=5,
            notes="Test",
        )
        assert sc.personalisation == 1
        assert sc.clarity == 10


class TestEmailResponse:
    def test_round_trip_from_attributes(self):
        class FakeEmail:
            id = 1
            timestamp = datetime(2026, 1, 1)
            from_name = "Alice"
            from_email = "alice@example.com"
            to_name = "Bob"
            to_email = "bob@example.com"
            subject = "Hello"
            body_text = "Hi there"
            direction = "EMAIL"
            hubspot_id = "hs-123"
            fetched_at = datetime(2026, 1, 2)

        resp = EmailResponse.model_validate(FakeEmail(), from_attributes=True)
        assert resp.id == 1
        assert resp.from_email == "alice@example.com"
        assert resp.subject == "Hello"
        assert resp.direction == "EMAIL"
