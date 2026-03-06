import pytest
from pydantic import ValidationError

from app.schemas.chain_score import ChainScoreCreate, ChainScoringResult


class TestChainScoreCreate:
    def test_rejects_progression_score_of_zero(self):
        with pytest.raises(ValidationError):
            ChainScoreCreate(
                chain_id=1,
                progression=0,
                responsiveness=5,
                persistence=5,
                conversation_quality=5,
            )

    def test_rejects_progression_score_of_eleven(self):
        with pytest.raises(ValidationError):
            ChainScoreCreate(
                chain_id=1,
                progression=11,
                responsiveness=5,
                persistence=5,
                conversation_quality=5,
            )

    def test_accepts_scores_at_boundaries(self):
        low = ChainScoreCreate(
            chain_id=1,
            progression=1,
            responsiveness=1,
            persistence=1,
            conversation_quality=1,
        )
        assert low.progression == 1

        high = ChainScoreCreate(
            chain_id=1,
            progression=10,
            responsiveness=10,
            persistence=10,
            conversation_quality=10,
        )
        assert high.progression == 10


class TestChainScoringResult:
    def test_requires_all_four_dimensions_and_notes(self):
        result = ChainScoringResult(
            progression=7,
            responsiveness=8,
            persistence=6,
            conversation_quality=7,
            notes="Good conversation flow",
        )
        assert result.progression == 7
        assert result.responsiveness == 8
        assert result.persistence == 6
        assert result.conversation_quality == 7
        assert result.notes == "Good conversation flow"

    def test_rejects_missing_progression(self):
        with pytest.raises(ValidationError):
            ChainScoringResult(
                responsiveness=8,
                persistence=6,
                conversation_quality=7,
                notes="Missing progression",
            )

    def test_rejects_missing_responsiveness(self):
        with pytest.raises(ValidationError):
            ChainScoringResult(
                progression=7,
                persistence=6,
                conversation_quality=7,
                notes="Missing responsiveness",
            )

    def test_rejects_missing_persistence(self):
        with pytest.raises(ValidationError):
            ChainScoringResult(
                progression=7,
                responsiveness=8,
                conversation_quality=7,
                notes="Missing persistence",
            )

    def test_rejects_missing_conversation_quality(self):
        with pytest.raises(ValidationError):
            ChainScoringResult(
                progression=7,
                responsiveness=8,
                persistence=6,
                notes="Missing conversation_quality",
            )

    def test_rejects_missing_notes(self):
        with pytest.raises(ValidationError):
            ChainScoringResult(
                progression=7,
                responsiveness=8,
                persistence=6,
                conversation_quality=7,
            )
