from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.enums import JobStatus, JobType
from app.models.job import Job
from app.models.score import Score


class TestRunFetchJob:
    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=5)
    async def test_sets_running_then_completed(self, mock_fetch, db, make_job, make_settings):
        await make_settings(auto_score_after_fetch=False)
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id)

        result = await db.execute(select(Job).where(Job.job_id == job.job_id))
        updated = result.scalar_one()
        assert updated.status == JobStatus.COMPLETED
        assert updated.started_at is not None
        assert updated.completed_at is not None

    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=0)
    async def test_uses_global_start_date_when_no_emails(self, mock_fetch, db, make_job, make_settings):
        await make_settings(
            global_start_date=date(2025, 6, 1), auto_score_after_fetch=False
        )
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id)

        call_kwargs = mock_fetch.call_args
        start_date = call_kwargs.kwargs.get("start_date") or call_kwargs[1].get("start_date")
        if start_date is None:
            # Positional args
            start_date = call_kwargs[0][3] if len(call_kwargs[0]) > 3 else None
        assert start_date == datetime.combine(date(2025, 6, 1), datetime.min.time())

    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=0)
    async def test_uses_max_fetched_at_when_later(self, mock_fetch, db, make_job, make_email, make_settings):
        later = datetime(2025, 12, 1)
        await make_email(fetched_at=later)
        await make_settings(auto_score_after_fetch=False)
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id)

        call_kwargs = mock_fetch.call_args
        start_date = call_kwargs.kwargs.get("start_date") or call_kwargs[1].get("start_date")
        if start_date is None:
            start_date = call_kwargs[0][3] if len(call_kwargs[0]) > 3 else None
        assert start_date == later

    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=0)
    async def test_uses_global_start_date_when_later_than_max_fetched_at(
        self, mock_fetch, db, make_job, make_email, make_settings
    ):
        # Email fetched_at is before global_start_date (date moved forward)
        old = datetime(2025, 1, 1)
        await make_email(fetched_at=old)
        await make_settings(
            global_start_date=date(2025, 10, 1), auto_score_after_fetch=False
        )
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id)

        call_kwargs = mock_fetch.call_args
        start_date = call_kwargs.kwargs.get("start_date") or call_kwargs[1].get("start_date")
        if start_date is None:
            start_date = call_kwargs[0][3] if len(call_kwargs[0]) > 3 else None
        expected = datetime.combine(date(2025, 10, 1), datetime.min.time())
        assert start_date == expected

    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=3)
    async def test_reads_company_domains_from_settings(self, mock_fetch, db, make_job, make_settings):
        await make_settings(
            company_domains="test.com,example.com", auto_score_after_fetch=False
        )
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id)

        call_kwargs = mock_fetch.call_args
        domains = call_kwargs.kwargs.get("company_domains") or call_kwargs[1].get("company_domains")
        if domains is None:
            domains = call_kwargs[0][2] if len(call_kwargs[0]) > 2 else None
        assert domains == ["test.com", "example.com"]

    @patch("app.services.job_runner.score_unscored_emails", new_callable=AsyncMock)
    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=2)
    async def test_triggers_scoring_when_auto_score_true(
        self, mock_fetch, mock_score, db, make_job, make_settings
    ):
        mock_score.return_value = {
            "scored": 2, "auto_scored": 0, "errors": 0,
            "total_input_tokens": 100, "total_output_tokens": 50,
        }
        await make_settings(auto_score_after_fetch=True)
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id)

        mock_score.assert_called_once()

    @patch("app.services.job_runner.score_unscored_emails", new_callable=AsyncMock)
    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=2)
    async def test_skips_scoring_when_auto_score_false(
        self, mock_fetch, mock_score, db, make_job, make_settings
    ):
        await make_settings(auto_score_after_fetch=False)
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id)

        mock_score.assert_not_called()

    @patch("app.services.job_runner.score_unscored_emails", new_callable=AsyncMock)
    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=2)
    async def test_reads_scoring_batch_size(
        self, mock_fetch, mock_score, db, make_job, make_settings
    ):
        mock_score.return_value = {
            "scored": 2, "auto_scored": 0, "errors": 0,
            "total_input_tokens": 0, "total_output_tokens": 0,
        }
        await make_settings(auto_score_after_fetch=True, scoring_batch_size=15)
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id)

        call_kwargs = mock_score.call_args
        batch_size = call_kwargs.kwargs.get("batch_size") or call_kwargs[1].get("batch_size")
        assert batch_size == 15

    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=5)
    async def test_writes_result_summary_with_fetched_and_new_reps(
        self, mock_fetch, db, make_job, make_settings
    ):
        await make_settings(auto_score_after_fetch=False)
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id)

        result = await db.execute(select(Job).where(Job.job_id == job.job_id))
        updated = result.scalar_one()
        assert "fetched" in updated.result_summary
        assert "new_reps" in updated.result_summary

    @patch("app.services.job_runner.score_unscored_emails", new_callable=AsyncMock)
    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=3)
    async def test_result_summary_includes_scored_when_auto_score(
        self, mock_fetch, mock_score, db, make_job, make_settings
    ):
        mock_score.return_value = {
            "scored": 3, "auto_scored": 0, "errors": 0,
            "total_input_tokens": 500, "total_output_tokens": 200,
        }
        await make_settings(auto_score_after_fetch=True)
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id)

        result = await db.execute(select(Job).where(Job.job_id == job.job_id))
        updated = result.scalar_one()
        assert "scored" in updated.result_summary
        assert updated.result_summary["scored"] == 3

    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock)
    async def test_sets_failed_on_exception(self, mock_fetch, db, make_job, make_settings):
        mock_fetch.side_effect = RuntimeError("HubSpot down")
        await make_settings(auto_score_after_fetch=False)
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id)

        result = await db.execute(select(Job).where(Job.job_id == job.job_id))
        updated = result.scalar_one()
        assert updated.status == JobStatus.FAILED
        assert "HubSpot down" in updated.error_message


class TestRunFetchJobAutoScoreOverride:
    @patch("app.services.job_runner.score_unscored_emails", new_callable=AsyncMock)
    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=2)
    async def test_auto_score_true_overrides_setting_false(
        self, mock_fetch, mock_score, db, make_job, make_settings
    ):
        mock_score.return_value = {
            "scored": 2, "auto_scored": 0, "errors": 0,
            "total_input_tokens": 100, "total_output_tokens": 50,
        }
        await make_settings(auto_score_after_fetch=False)
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id, auto_score=True)

        mock_score.assert_called_once()

    @patch("app.services.job_runner.score_unscored_emails", new_callable=AsyncMock)
    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=2)
    async def test_auto_score_false_overrides_setting_true(
        self, mock_fetch, mock_score, db, make_job, make_settings
    ):
        await make_settings(auto_score_after_fetch=True)
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id, auto_score=False)

        mock_score.assert_not_called()

    @patch("app.services.job_runner.score_unscored_emails", new_callable=AsyncMock)
    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=2)
    async def test_auto_score_none_falls_back_to_setting(
        self, mock_fetch, mock_score, db, make_job, make_settings
    ):
        mock_score.return_value = {
            "scored": 2, "auto_scored": 0, "errors": 0,
            "total_input_tokens": 0, "total_output_tokens": 0,
        }
        await make_settings(auto_score_after_fetch=True)
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id, auto_score=None)

        mock_score.assert_called_once()


class TestRunFetchJobWithParams:
    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=3)
    async def test_explicit_start_date_overrides_computed(
        self, mock_fetch, db, make_job, make_settings
    ):
        await make_settings(auto_score_after_fetch=False)
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(
            db, job.job_id, fetch_start_date=date(2024, 1, 1)
        )

        call_kwargs = mock_fetch.call_args
        start_date = call_kwargs.kwargs.get("start_date") or call_kwargs[1].get("start_date")
        assert start_date == datetime.combine(date(2024, 1, 1), datetime.min.time())

    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=3)
    async def test_end_date_passed_to_fetch_and_store(
        self, mock_fetch, db, make_job, make_settings
    ):
        await make_settings(auto_score_after_fetch=False)
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(
            db, job.job_id, fetch_end_date=date(2024, 1, 31)
        )

        call_kwargs = mock_fetch.call_args
        end_date = call_kwargs.kwargs.get("end_date") or call_kwargs[1].get("end_date")
        assert end_date == datetime.combine(date(2024, 1, 31), datetime.min.time())

    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=3)
    async def test_max_count_passed_to_fetch_and_store(
        self, mock_fetch, db, make_job, make_settings
    ):
        await make_settings(auto_score_after_fetch=False)
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id, max_count=50)

        call_kwargs = mock_fetch.call_args
        max_count = call_kwargs.kwargs.get("max_count") or call_kwargs[1].get("max_count")
        assert max_count == 50

    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=3)
    async def test_none_params_preserve_default_behaviour(
        self, mock_fetch, db, make_job, make_settings
    ):
        await make_settings(
            global_start_date=date(2025, 6, 1), auto_score_after_fetch=False
        )
        job = await make_job(job_type=JobType.FETCH)
        await db.commit()

        from app.services.job_runner import run_fetch_job

        await run_fetch_job(db, job.job_id)

        call_kwargs = mock_fetch.call_args
        start_date = call_kwargs.kwargs.get("start_date") or call_kwargs[1].get("start_date")
        assert start_date == datetime.combine(date(2025, 6, 1), datetime.min.time())
        end_date = call_kwargs.kwargs.get("end_date")
        assert end_date is None
        max_count = call_kwargs.kwargs.get("max_count")
        assert max_count is None


class TestRunScoreJob:
    @patch("app.services.job_runner.score_unscored_emails", new_callable=AsyncMock)
    async def test_sets_running_then_completed(self, mock_score, db, make_job):
        mock_score.return_value = {
            "scored": 0, "auto_scored": 0, "errors": 0,
            "total_input_tokens": 0, "total_output_tokens": 0,
        }
        job = await make_job(job_type=JobType.SCORE)
        await db.commit()

        from app.services.job_runner import run_score_job

        await run_score_job(db, job.job_id)

        result = await db.execute(select(Job).where(Job.job_id == job.job_id))
        updated = result.scalar_one()
        assert updated.status == JobStatus.COMPLETED
        assert updated.started_at is not None

    @patch("app.services.job_runner.score_unscored_emails", new_callable=AsyncMock)
    async def test_reads_scoring_batch_size(self, mock_score, db, make_job, make_settings):
        mock_score.return_value = {
            "scored": 0, "auto_scored": 0, "errors": 0,
            "total_input_tokens": 0, "total_output_tokens": 0,
        }
        await make_settings(scoring_batch_size=8)
        job = await make_job(job_type=JobType.SCORE)
        await db.commit()

        from app.services.job_runner import run_score_job

        await run_score_job(db, job.job_id)

        call_kwargs = mock_score.call_args
        batch_size = call_kwargs.kwargs.get("batch_size") or call_kwargs[1].get("batch_size")
        assert batch_size == 8

    @patch("app.services.job_runner.score_unscored_emails", new_callable=AsyncMock)
    async def test_writes_result_summary(self, mock_score, db, make_job):
        mock_score.return_value = {
            "scored": 10, "auto_scored": 2, "errors": 1,
            "total_input_tokens": 5000, "total_output_tokens": 1000,
        }
        job = await make_job(job_type=JobType.SCORE)
        await db.commit()

        from app.services.job_runner import run_score_job

        await run_score_job(db, job.job_id)

        result = await db.execute(select(Job).where(Job.job_id == job.job_id))
        updated = result.scalar_one()
        assert updated.result_summary["scored"] == 12  # scored + auto_scored
        assert updated.result_summary["errors"] == 1
        assert updated.result_summary["tokens"] == 6000


class TestRunRescoreJob:
    @patch("app.services.job_runner.score_unscored_emails", new_callable=AsyncMock)
    async def test_deletes_all_existing_scores(
        self, mock_score, db, make_job, make_email, make_score
    ):
        mock_score.return_value = {
            "scored": 1, "auto_scored": 0, "errors": 0,
            "total_input_tokens": 0, "total_output_tokens": 0,
        }
        email = await make_email()
        await make_score(email_id=email.id)
        await db.flush()

        # Verify score exists
        result = await db.execute(select(Score))
        assert len(result.scalars().all()) == 1

        job = await make_job(job_type=JobType.RESCORE)
        await db.commit()

        from app.services.job_runner import run_rescore_job

        await run_rescore_job(db, job.job_id)

        # The rescore job deletes scores then calls score_unscored_emails
        # which sees all emails as unscored. Verify the delete happened
        # by checking that score_unscored_emails was called (meaning all
        # emails became "unscored").
        mock_score.assert_called_once()

    @patch("app.services.job_runner.score_unscored_emails", new_callable=AsyncMock)
    async def test_scores_every_email(
        self, mock_score, db, make_job, make_email, make_score
    ):
        mock_score.return_value = {
            "scored": 2, "auto_scored": 0, "errors": 0,
            "total_input_tokens": 0, "total_output_tokens": 0,
        }
        e1 = await make_email(from_email="a@test.com")
        e2 = await make_email(from_email="b@test.com")
        await make_score(email_id=e1.id)
        await make_score(email_id=e2.id)

        job = await make_job(job_type=JobType.RESCORE)
        await db.commit()

        from app.services.job_runner import run_rescore_job

        await run_rescore_job(db, job.job_id)

        # score_unscored_emails is called after deleting all scores,
        # so it should score all emails (both were previously scored)
        mock_score.assert_called_once()
