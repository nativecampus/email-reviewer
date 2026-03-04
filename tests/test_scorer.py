import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select

from app.models.email import Email
from app.models.score import Score
from app.services.scorer import _build_user_message, _score_single_email, score_unscored_emails


class TestBuildUserMessage:
    def test_includes_all_metadata_fields(self, make_email):
        email = Email(
            from_email="alice@example.com",
            from_name="Alice",
            to_email="bob@example.com",
            to_name="Bob",
            subject="Hello Bob",
            body_text="This is the body.",
            timestamp=datetime(2026, 3, 1, 12, 0, 0),
        )
        result = _build_user_message(email)
        assert "alice@example.com" in result
        assert "bob@example.com" in result
        assert "Hello Bob" in result
        assert "This is the body." in result
        assert "From:" in result
        assert "To:" in result
        assert "Subject:" in result
        assert "Date:" in result
        assert "Body:" in result

    def test_truncates_body_over_4000_chars(self):
        long_body = "x" * 5000
        email = Email(from_email="a@b.com", body_text=long_body)
        result = _build_user_message(email)
        assert "x" * 4000 in result
        assert "x" * 4001 not in result

    def test_handles_none_body_text(self):
        email = Email(from_email="a@b.com", body_text=None)
        result = _build_user_message(email)
        assert "Body:" in result


class TestScoreSingleEmail:
    async def test_parses_valid_json_response(self):
        valid_json = json.dumps({
            "personalisation": 7,
            "clarity": 8,
            "value_proposition": 6,
            "cta": 5,
            "overall": 7,
            "notes": "Good email overall.",
        })
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=valid_json)]
        mock_usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_message.usage = mock_usage

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        email = Email(id=1, from_email="a@b.com", body_text="Hello there")
        semaphore = asyncio.Semaphore(5)

        result = await _score_single_email(mock_client, email, semaphore)

        assert result is not None
        assert result.personalisation == 7
        assert result.clarity == 8
        assert result.value_proposition == 6
        assert result.cta == 5
        assert result.overall == 7
        assert result.notes == "Good email overall."

    async def test_retries_once_on_invalid_json_then_succeeds(self):
        valid_json = json.dumps({
            "personalisation": 5,
            "clarity": 6,
            "value_proposition": 7,
            "cta": 8,
            "overall": 6,
            "notes": "Decent.",
        })
        garbage_message = MagicMock()
        garbage_message.content = [MagicMock(text="not valid json {{{")]
        garbage_message.usage = MagicMock(input_tokens=100, output_tokens=50)

        valid_message = MagicMock()
        valid_message.content = [MagicMock(text=valid_json)]
        valid_message.usage = MagicMock(input_tokens=100, output_tokens=50)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=[garbage_message, valid_message])

        email = Email(id=2, from_email="a@b.com", body_text="Test body")
        semaphore = asyncio.Semaphore(5)

        result = await _score_single_email(mock_client, email, semaphore)

        assert result is not None
        assert result.personalisation == 5
        assert mock_client.messages.create.call_count == 2

    async def test_sets_score_error_after_two_failures(self):
        garbage_message = MagicMock()
        garbage_message.content = [MagicMock(text="garbage")]
        garbage_message.usage = MagicMock(input_tokens=100, output_tokens=50)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=garbage_message)

        email = Email(id=3, from_email="a@b.com", body_text="Test body")
        semaphore = asyncio.Semaphore(5)

        result = await _score_single_email(mock_client, email, semaphore)

        assert result is None
        assert mock_client.messages.create.call_count == 2


class TestScoreUnscoredEmails:
    async def test_skips_already_scored_emails(self, db, make_email, make_score):
        email = await make_email(from_email="rep@example.com", body_text="Some content here for testing the scorer service")
        await make_score(email_id=email.id)

        with patch("app.services.scorer.AsyncAnthropic") as mock_cls:
            summary = await score_unscored_emails(db)

        mock_cls.assert_not_called()
        assert summary["scored"] == 0

    async def test_auto_scores_empty_body_as_all_ones(self, db, make_email):
        await make_email(from_email="rep@example.com", body_text=None)

        with patch("app.services.scorer.AsyncAnthropic") as mock_cls:
            summary = await score_unscored_emails(db)

        mock_cls.assert_not_called()
        assert summary["auto_scored"] == 1

        result = await db.execute(select(Score))
        score = result.scalar_one()
        assert score.personalisation == 1
        assert score.clarity == 1
        assert score.value_proposition == 1
        assert score.cta == 1
        assert score.overall == 1
        assert score.score_error is False
        assert "empty" in score.notes.lower() or "no body" in score.notes.lower()

    async def test_auto_scores_short_body_as_all_ones(self, db, make_email):
        await make_email(from_email="rep@example.com", body_text="Too short to score")

        with patch("app.services.scorer.AsyncAnthropic") as mock_cls:
            summary = await score_unscored_emails(db)

        mock_cls.assert_not_called()
        assert summary["auto_scored"] == 1

        result = await db.execute(select(Score))
        score = result.scalar_one()
        assert score.personalisation == 1
        assert score.clarity == 1
        assert score.value_proposition == 1
        assert score.cta == 1
        assert score.overall == 1
        assert score.score_error is False
        assert "short" in score.notes.lower() or "under 20" in score.notes.lower() or "word" in score.notes.lower()
