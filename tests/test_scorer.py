import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from anthropic import RateLimitError
from sqlalchemy import select

from app.models.chain_score import ChainScore
from app.models.email import Email
from app.models.score import Score
from app.services.scorer import (
    _build_chain_context,
    _build_user_message,
    _calculate_weighted_overall,
    _score_single_email,
    score_unscored_chains,
    score_unscored_emails,
)


def _make_mock_claude_response(json_data):
    """Build a mock Claude API response object."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(json_data))]
    mock_message.usage = MagicMock(input_tokens=100, output_tokens=50)
    return mock_message


def _make_mock_client(response):
    """Build a mock AsyncAnthropic client returning a fixed response."""
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=response)
    return mock_client


class TestCalculateWeightedOverall:
    def test_default_weights(self):
        scores = {
            "value_proposition": 8,
            "personalisation": 6,
            "cta": 7,
            "clarity": 9,
        }
        weights = {
            "weight_value_proposition": 0.35,
            "weight_personalisation": 0.30,
            "weight_cta": 0.20,
            "weight_clarity": 0.15,
        }
        # 8*0.35 + 6*0.30 + 7*0.20 + 9*0.15 = 2.80 + 1.80 + 1.40 + 1.35 = 7.35 -> 7
        result = _calculate_weighted_overall(scores, weights)
        assert result == 7

    def test_rounds_half_up(self):
        # Engineer scores/weights so result is exactly 7.5 -> should round to 8
        scores = {
            "value_proposition": 10,
            "personalisation": 5,
            "cta": 10,
            "clarity": 0,
        }
        weights = {
            "weight_value_proposition": 0.50,
            "weight_personalisation": 0.50,
            "weight_cta": 0.00,
            "weight_clarity": 0.00,
        }
        # 10*0.5 + 5*0.5 = 7.5 -> 8
        result = _calculate_weighted_overall(scores, weights)
        assert result == 8

    def test_custom_weights(self):
        scores = {
            "value_proposition": 10,
            "personalisation": 10,
            "cta": 10,
            "clarity": 10,
        }
        weights = {
            "weight_value_proposition": 0.25,
            "weight_personalisation": 0.25,
            "weight_cta": 0.25,
            "weight_clarity": 0.25,
        }
        result = _calculate_weighted_overall(scores, weights)
        assert result == 10

    def test_clamps_above_10(self):
        scores = {
            "value_proposition": 100,
            "personalisation": 100,
            "cta": 100,
            "clarity": 100,
        }
        weights = {
            "weight_value_proposition": 0.25,
            "weight_personalisation": 0.25,
            "weight_cta": 0.25,
            "weight_clarity": 0.25,
        }
        result = _calculate_weighted_overall(scores, weights)
        assert result == 10

    def test_clamps_below_1(self):
        scores = {
            "value_proposition": 0,
            "personalisation": 0,
            "cta": 0,
            "clarity": 0,
        }
        weights = {
            "weight_value_proposition": 0.25,
            "weight_personalisation": 0.25,
            "weight_cta": 0.25,
            "weight_clarity": 0.25,
        }
        result = _calculate_weighted_overall(scores, weights)
        assert result == 1


class TestPromptLoading:
    async def test_uses_initial_prompt_for_email_without_chain(self, db, make_email, make_settings):
        settings = await make_settings(initial_email_prompt="Custom initial prompt")
        email = await make_email(
            from_email="rep@example.com",
            body_text="This is a sufficiently long body text for scoring purposes to pass the minimum word count",
        )

        valid_response = _make_mock_claude_response({
            "personalisation": 7, "clarity": 8,
            "value_proposition": 6, "cta": 5, "notes": "Good.",
        })
        mock_client = _make_mock_client(valid_response)
        semaphore = asyncio.Semaphore(5)

        await _score_single_email(mock_client, email, semaphore, settings)

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == [{"type": "text", "text": "Custom initial prompt"}]

    async def test_uses_chain_prompt_for_followup_email(self, db, make_email, make_chain, make_settings):
        settings = await make_settings(chain_email_prompt="Custom chain prompt")
        chain = await make_chain()
        # Position 1 email in the chain
        await make_email(
            from_email="rep@example.com",
            body_text="First email body text with enough words to pass the minimum word count check",
            chain_id=chain.id,
            position_in_chain=1,
            subject="Test Subject",
            timestamp=datetime(2026, 3, 1),
        )
        # The email being scored is at position 3
        email = await make_email(
            from_email="rep@example.com",
            body_text="Follow up email body text with enough words to pass the minimum word count check",
            chain_id=chain.id,
            position_in_chain=3,
            subject="Re: Test Subject",
            timestamp=datetime(2026, 3, 3),
        )

        valid_response = _make_mock_claude_response({
            "personalisation": 7, "clarity": 8,
            "value_proposition": 6, "cta": 5, "notes": "Good.",
        })
        mock_client = _make_mock_client(valid_response)
        semaphore = asyncio.Semaphore(5)

        await _score_single_email(mock_client, email, semaphore, settings)

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == [{"type": "text", "text": "Custom chain prompt"}]


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

    def test_includes_chain_context_for_followup(self):
        email = Email(
            from_email="a@b.com",
            body_text="Follow up body",
            position_in_chain=2,
            chain_id=1,
        )
        email._chain_context = "Previous email content"
        result = _build_user_message(email)
        assert "Previous conversation" in result
        assert "Previous email content" in result

    def test_no_chain_context_for_first_email(self):
        email = Email(
            from_email="a@b.com",
            body_text="First body",
            position_in_chain=1,
        )
        result = _build_user_message(email)
        assert "Previous conversation" not in result

    def test_no_chain_context_when_no_position(self):
        email = Email(
            from_email="a@b.com",
            body_text="Solo body",
            position_in_chain=None,
        )
        result = _build_user_message(email)
        assert "Previous conversation" not in result


class TestBuildChainContext:
    async def test_returns_empty_when_no_chain(self, db):
        email = Email(from_email="a@b.com", chain_id=None, position_in_chain=None)
        result = await _build_chain_context(db, email)
        assert result == ""

    async def test_returns_formatted_prior_emails(self, db, make_chain, make_email):
        chain = await make_chain()
        await make_email(
            from_email="rep@example.com",
            to_email="client@example.com",
            subject="Hello",
            body_text="First email body",
            chain_id=chain.id,
            position_in_chain=1,
            timestamp=datetime(2026, 3, 1),
        )
        await make_email(
            from_email="client@example.com",
            to_email="rep@example.com",
            subject="Re: Hello",
            body_text="Second email body",
            chain_id=chain.id,
            position_in_chain=2,
            timestamp=datetime(2026, 3, 2),
        )
        current_email = await make_email(
            from_email="rep@example.com",
            to_email="client@example.com",
            subject="Re: Hello",
            body_text="Third email body",
            chain_id=chain.id,
            position_in_chain=3,
            timestamp=datetime(2026, 3, 3),
        )

        result = await _build_chain_context(db, current_email)
        assert "First email body" in result
        assert "Second email body" in result
        assert "Third email body" not in result
        assert "From:" in result
        assert "To:" in result

    async def test_truncates_individual_emails_to_2000_chars(self, db, make_chain, make_email):
        chain = await make_chain()
        long_body = "x" * 3000
        await make_email(
            from_email="rep@example.com",
            body_text=long_body,
            chain_id=chain.id,
            position_in_chain=1,
            timestamp=datetime(2026, 3, 1),
        )
        current_email = await make_email(
            from_email="rep@example.com",
            body_text="Current email",
            chain_id=chain.id,
            position_in_chain=2,
            timestamp=datetime(2026, 3, 2),
        )

        result = await _build_chain_context(db, current_email)
        assert "x" * 2000 in result
        assert "x" * 2001 not in result


class TestScoreSingleEmail:
    async def test_parses_valid_json_response(self, db, make_settings):
        settings = await make_settings()
        valid_response = _make_mock_claude_response({
            "personalisation": 7, "clarity": 8,
            "value_proposition": 6, "cta": 5, "notes": "Good email.",
        })
        mock_client = _make_mock_client(valid_response)
        email = Email(id=1, from_email="a@b.com", body_text="Hello there")
        semaphore = asyncio.Semaphore(5)

        result = await _score_single_email(mock_client, email, semaphore, settings)

        assert result is not None
        assert result.personalisation == 7
        assert result.clarity == 8
        assert result.value_proposition == 6
        assert result.cta == 5
        assert result.notes == "Good email."

    async def test_retries_once_on_invalid_json_then_succeeds(self, db, make_settings):
        settings = await make_settings()
        valid_json = json.dumps({
            "personalisation": 5, "clarity": 6,
            "value_proposition": 7, "cta": 8, "notes": "Decent.",
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

        result = await _score_single_email(mock_client, email, semaphore, settings)

        assert result is not None
        assert result.personalisation == 5
        assert mock_client.messages.create.call_count == 2

    async def test_sets_score_error_after_two_failures(self, db, make_settings):
        settings = await make_settings()
        garbage_message = MagicMock()
        garbage_message.content = [MagicMock(text="garbage")]
        garbage_message.usage = MagicMock(input_tokens=100, output_tokens=50)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=garbage_message)

        email = Email(id=3, from_email="a@b.com", body_text="Test body")
        semaphore = asyncio.Semaphore(5)

        result = await _score_single_email(mock_client, email, semaphore, settings)

        assert result is None
        assert mock_client.messages.create.call_count == 2

    @patch("app.services.scorer.asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_on_rate_limit_using_retry_after_header(self, mock_sleep, db, make_settings):
        settings = await make_settings()
        valid_response = _make_mock_claude_response({
            "personalisation": 7, "clarity": 8,
            "value_proposition": 6, "cta": 5, "notes": "Good email.",
        })

        rate_limit_response = MagicMock(status_code=429, headers={"retry-after": "42"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[
                RateLimitError(message="rate limited", response=rate_limit_response, body=None),
                valid_response,
            ]
        )

        email = Email(id=4, from_email="a@b.com", body_text="Test body content")
        semaphore = asyncio.Semaphore(5)

        result = await _score_single_email(mock_client, email, semaphore, settings)

        assert result is not None
        assert result.personalisation == 7
        mock_sleep.assert_called_once_with(42.0)

    @patch("app.services.scorer.asyncio.sleep", new_callable=AsyncMock)
    async def test_uses_default_delay_when_retry_after_header_missing(self, mock_sleep, db, make_settings):
        from app.services.scorer import DEFAULT_RETRY_AFTER

        settings = await make_settings()
        valid_response = _make_mock_claude_response({
            "personalisation": 5, "clarity": 5,
            "value_proposition": 5, "cta": 5, "notes": "Ok.",
        })

        no_header_response = MagicMock(status_code=429, headers={})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[
                RateLimitError(message="rate limited", response=no_header_response, body=None),
                valid_response,
            ]
        )

        email = Email(id=6, from_email="a@b.com", body_text="Test body content")
        semaphore = asyncio.Semaphore(5)

        result = await _score_single_email(mock_client, email, semaphore, settings)

        assert result is not None
        mock_sleep.assert_called_once_with(DEFAULT_RETRY_AFTER)

    @patch("app.services.scorer.asyncio.sleep", new_callable=AsyncMock)
    async def test_returns_none_after_all_rate_limit_retries_exhausted(self, mock_sleep, db, make_settings):
        settings = await make_settings()
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=RateLimitError(
                message="rate limited", response=MagicMock(status_code=429, headers={"retry-after": "5"}), body=None
            )
        )

        email = Email(id=5, from_email="a@b.com", body_text="Test body content")
        semaphore = asyncio.Semaphore(5)

        result = await _score_single_email(mock_client, email, semaphore, settings)

        assert result is None


class TestScoreUnscoredEmails:
    async def test_skips_already_scored_emails(self, db, make_email, make_score):
        email = await make_email(from_email="rep@example.com", body_text="Some content here for testing the scorer service")
        await make_score(email_id=email.id)

        with patch("app.services.scorer.AsyncAnthropic") as mock_cls:
            summary = await score_unscored_emails(db)

        mock_cls.assert_not_called()
        assert summary["scored"] == 0

    async def test_skips_empty_body_without_creating_score(self, db, make_email):
        await make_email(from_email="rep@example.com", body_text=None)

        with patch("app.services.scorer.AsyncAnthropic") as mock_cls:
            summary = await score_unscored_emails(db)

        mock_cls.assert_not_called()
        assert summary["skipped"] == 1

        result = await db.execute(select(Score))
        assert result.scalars().all() == []

    async def test_skips_short_body_without_creating_score(self, db, make_email):
        await make_email(from_email="rep@example.com", body_text="Too short to score")

        with patch("app.services.scorer.AsyncAnthropic") as mock_cls:
            summary = await score_unscored_emails(db)

        mock_cls.assert_not_called()
        assert summary["skipped"] == 1

        result = await db.execute(select(Score))
        assert result.scalars().all() == []

    async def test_stores_calculated_overall_not_claude_value(self, db, make_email, make_settings):
        await make_settings()
        email = await make_email(
            from_email="rep@example.com",
            body_text="This is a sufficiently long body for testing the scoring service properly and completely to ensure it passes the minimum word count threshold easily",
        )

        email_response = _make_mock_claude_response({
            "personalisation": 6, "clarity": 9,
            "value_proposition": 8, "cta": 7, "notes": "Good.",
        })
        # score_unscored_emails also calls score_unscored_chains which creates
        # its own AsyncAnthropic, so we patch at module level to cover both.
        mock_client_instance = AsyncMock()
        mock_client_instance.messages.create = AsyncMock(return_value=email_response)
        with patch("app.services.scorer.AsyncAnthropic", return_value=mock_client_instance):
            summary = await score_unscored_emails(db)

        assert summary["scored"] == 1

        result = await db.execute(select(Score).where(Score.email_id == email.id))
        score = result.scalar_one()
        # 8*0.35 + 6*0.30 + 7*0.20 + 9*0.15 = 2.80 + 1.80 + 1.40 + 1.35 = 7.35 -> 7
        assert score.overall == 7
        assert score.personalisation == 6
        assert score.clarity == 9
        assert score.value_proposition == 8
        assert score.cta == 7


class TestScoreUnscoredChains:
    async def test_skips_chains_with_existing_score(self, db, make_chain, make_chain_score, make_email):
        chain = await make_chain(email_count=2, outgoing_count=2)
        await make_chain_score(chain_id=chain.id)
        await make_email(
            from_email="rep@example.com", chain_id=chain.id,
            position_in_chain=1, body_text="Email 1",
            timestamp=datetime(2026, 3, 1),
        )
        await make_email(
            from_email="rep@example.com", chain_id=chain.id,
            position_in_chain=2, body_text="Email 2",
            timestamp=datetime(2026, 3, 2),
        )

        with patch("app.services.scorer.AsyncAnthropic") as mock_cls:
            result = await score_unscored_chains(db)

        mock_cls.assert_not_called()
        assert result["chains_scored"] == 0

    async def test_skips_chains_with_fewer_than_2_emails(self, db, make_chain, make_email):
        chain = await make_chain(email_count=1, outgoing_count=1)
        await make_email(
            from_email="rep@example.com", chain_id=chain.id,
            position_in_chain=1, body_text="Solo email",
            timestamp=datetime(2026, 3, 1),
        )

        with patch("app.services.scorer.AsyncAnthropic") as mock_cls:
            result = await score_unscored_chains(db)

        mock_cls.assert_not_called()
        assert result["chains_scored"] == 0

    async def test_creates_chain_score_from_valid_response(self, db, make_chain, make_email, make_settings):
        settings = await make_settings()
        chain = await make_chain(email_count=2, outgoing_count=2)
        await make_email(
            from_email="rep@example.com", chain_id=chain.id,
            position_in_chain=1, body_text="First email content",
            timestamp=datetime(2026, 3, 1, 10, 0, 0),
            direction="EMAIL",
        )
        await make_email(
            from_email="rep@example.com", chain_id=chain.id,
            position_in_chain=2, body_text="Second email content",
            timestamp=datetime(2026, 3, 2, 10, 0, 0),
            direction="EMAIL",
        )

        valid_response = _make_mock_claude_response({
            "progression": 8, "responsiveness": 7,
            "persistence": 6, "conversation_quality": 9,
            "notes": "Good chain.",
        })
        mock_client_instance = _make_mock_client(valid_response)

        with patch("app.services.scorer.AsyncAnthropic", return_value=mock_client_instance):
            result = await score_unscored_chains(db)

        assert result["chains_scored"] == 1
        cs_result = await db.execute(select(ChainScore).where(ChainScore.chain_id == chain.id))
        chain_score = cs_result.scalar_one()
        assert chain_score.progression == 8
        assert chain_score.responsiveness == 7
        assert chain_score.persistence == 6
        assert chain_score.conversation_quality == 9
        assert chain_score.notes == "Good chain."

    async def test_computes_avg_response_hours(self, db, make_chain, make_email, make_settings):
        settings = await make_settings()
        chain = await make_chain(email_count=3, outgoing_count=3)
        await make_email(
            from_email="rep@example.com", chain_id=chain.id,
            position_in_chain=1, body_text="First",
            timestamp=datetime(2026, 3, 1, 10, 0, 0),
            direction="EMAIL",
        )
        await make_email(
            from_email="rep@example.com", chain_id=chain.id,
            position_in_chain=2, body_text="Second",
            timestamp=datetime(2026, 3, 2, 10, 0, 0),
            direction="EMAIL",
        )
        await make_email(
            from_email="rep@example.com", chain_id=chain.id,
            position_in_chain=3, body_text="Third",
            timestamp=datetime(2026, 3, 3, 22, 0, 0),
            direction="EMAIL",
        )

        valid_response = _make_mock_claude_response({
            "progression": 8, "responsiveness": 7,
            "persistence": 6, "conversation_quality": 9,
            "notes": "Good.",
        })
        mock_client_instance = _make_mock_client(valid_response)

        with patch("app.services.scorer.AsyncAnthropic", return_value=mock_client_instance):
            result = await score_unscored_chains(db)

        cs_result = await db.execute(select(ChainScore).where(ChainScore.chain_id == chain.id))
        chain_score = cs_result.scalar_one()
        # 24h between email 1 and 2, 36h between email 2 and 3 -> avg 30h
        assert chain_score.avg_response_hours == 30.0

    async def test_loads_chain_evaluation_prompt_from_settings(self, db, make_chain, make_email, make_settings):
        settings = await make_settings(chain_evaluation_prompt="Custom chain eval prompt")
        chain = await make_chain(email_count=2, outgoing_count=2)
        await make_email(
            from_email="rep@example.com", chain_id=chain.id,
            position_in_chain=1, body_text="Email 1",
            timestamp=datetime(2026, 3, 1),
            direction="EMAIL",
        )
        await make_email(
            from_email="rep@example.com", chain_id=chain.id,
            position_in_chain=2, body_text="Email 2",
            timestamp=datetime(2026, 3, 2),
            direction="EMAIL",
        )

        valid_response = _make_mock_claude_response({
            "progression": 8, "responsiveness": 7,
            "persistence": 6, "conversation_quality": 9,
            "notes": "Good.",
        })
        mock_client_instance = _make_mock_client(valid_response)

        with patch("app.services.scorer.AsyncAnthropic", return_value=mock_client_instance):
            result = await score_unscored_chains(db)

        call_kwargs = mock_client_instance.messages.create.call_args
        assert call_kwargs.kwargs["system"] == [{"type": "text", "text": "Custom chain eval prompt"}]

    async def test_sets_score_error_after_two_parse_failures(self, db, make_chain, make_email, make_settings):
        settings = await make_settings()
        chain = await make_chain(email_count=2, outgoing_count=2)
        await make_email(
            from_email="rep@example.com", chain_id=chain.id,
            position_in_chain=1, body_text="Email 1",
            timestamp=datetime(2026, 3, 1),
            direction="EMAIL",
        )
        await make_email(
            from_email="rep@example.com", chain_id=chain.id,
            position_in_chain=2, body_text="Email 2",
            timestamp=datetime(2026, 3, 2),
            direction="EMAIL",
        )

        garbage_message = MagicMock()
        garbage_message.content = [MagicMock(text="not json")]
        garbage_message.usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_client_instance = AsyncMock()
        mock_client_instance.messages.create = AsyncMock(return_value=garbage_message)

        with patch("app.services.scorer.AsyncAnthropic", return_value=mock_client_instance):
            result = await score_unscored_chains(db)

        assert result["errors"] == 1
        cs_result = await db.execute(select(ChainScore).where(ChainScore.chain_id == chain.id))
        chain_score = cs_result.scalar_one()
        assert chain_score.score_error is True

    async def test_handles_chain_with_zero_outgoing_emails(self, db, make_chain, make_email, make_settings):
        settings = await make_settings()
        chain = await make_chain(email_count=2, outgoing_count=0, incoming_count=2)
        await make_email(
            from_email="client@example.com", chain_id=chain.id,
            position_in_chain=1, body_text="Incoming 1",
            timestamp=datetime(2026, 3, 1),
            direction="INCOMING_EMAIL",
        )
        await make_email(
            from_email="client@example.com", chain_id=chain.id,
            position_in_chain=2, body_text="Incoming 2",
            timestamp=datetime(2026, 3, 2),
            direction="INCOMING_EMAIL",
        )

        valid_response = _make_mock_claude_response({
            "progression": 5, "responsiveness": 5,
            "persistence": 5, "conversation_quality": 5,
            "notes": "No outgoing.",
        })
        mock_client_instance = _make_mock_client(valid_response)

        with patch("app.services.scorer.AsyncAnthropic", return_value=mock_client_instance):
            result = await score_unscored_chains(db)

        cs_result = await db.execute(select(ChainScore).where(ChainScore.chain_id == chain.id))
        chain_score = cs_result.scalar_one()
        assert chain_score.avg_response_hours is None


class TestRunRescoreJob:
    async def test_deletes_chain_scores_before_rescoring(self, db, make_chain, make_chain_score, make_email, make_score, make_job):
        # Chain with only 1 email so it won't be re-scored by score_unscored_chains
        chain = await make_chain(email_count=1, outgoing_count=1)
        await make_chain_score(chain_id=chain.id)
        email = await make_email(
            from_email="rep@example.com",
            body_text="Enough words here for a real scoring test to pass the minimum word count requirement",
            chain_id=chain.id,
            position_in_chain=1,
        )
        await make_score(email_id=email.id)

        # Verify chain_scores and scores exist before rescore
        cs_before = await db.execute(select(ChainScore))
        assert len(cs_before.scalars().all()) == 1
        s_before = await db.execute(select(Score))
        assert len(s_before.scalars().all()) == 1

        job = await make_job(job_type="RESCORE")

        valid_response = _make_mock_claude_response({
            "personalisation": 7, "clarity": 8,
            "value_proposition": 6, "cta": 5, "notes": "Re-scored.",
        })
        mock_client_instance = _make_mock_client(valid_response)

        with patch("app.services.scorer.AsyncAnthropic", return_value=mock_client_instance):
            from app.services.job_runner import run_rescore_job
            await run_rescore_job(db, job.job_id)

        # Chain scores should have been deleted (chain has only 1 email, not re-scored)
        cs_after = await db.execute(select(ChainScore))
        assert len(cs_after.scalars().all()) == 0
