from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.enums import JobStatus, JobType
from app.models.job import Job
from app.worker import redis_available
from tests.conftest import TestingSessionLocal


class TestPostOperations:
    @patch("app.routers.operations.run_fetch_job", new_callable=AsyncMock)
    async def test_fetch_returns_202(self, mock_run, client):
        resp = await client.post("/api/operations/fetch")
        assert resp.status_code == 202
        assert "job_id" in resp.json()

    @patch("app.routers.operations.run_score_job", new_callable=AsyncMock)
    async def test_score_returns_202(self, mock_run, client):
        resp = await client.post("/api/operations/score")
        assert resp.status_code == 202
        assert "job_id" in resp.json()

    @patch("app.routers.operations.run_rescore_job", new_callable=AsyncMock)
    async def test_rescore_returns_202(self, mock_run, client):
        resp = await client.post("/api/operations/rescore")
        assert resp.status_code == 202
        assert "job_id" in resp.json()

    @patch("app.routers.operations.run_export_job", new_callable=AsyncMock)
    async def test_export_returns_202(self, mock_run, client):
        resp = await client.post("/api/operations/export")
        assert resp.status_code == 202
        assert "job_id" in resp.json()


class TestGetJobs:
    @patch("app.routers.operations.run_fetch_job", new_callable=AsyncMock)
    async def test_list_jobs_ordered_by_created_at_desc(self, mock_run, client):
        await client.post("/api/operations/fetch")
        await client.post("/api/operations/fetch")
        resp = await client.get("/api/operations/jobs")
        assert resp.status_code == 200
        jobs = resp.json()
        assert len(jobs) >= 2
        # Most recent first
        assert jobs[0]["created_at"] >= jobs[1]["created_at"]

    @patch("app.routers.operations.run_fetch_job", new_callable=AsyncMock)
    async def test_get_job_detail(self, mock_run, client):
        create_resp = await client.post("/api/operations/fetch")
        job_id = create_resp.json()["job_id"]
        resp = await client.get(f"/api/operations/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] == "PENDING"

    async def test_get_job_returns_404_for_nonexistent(self, client):
        resp = await client.get("/api/operations/jobs/99999")
        assert resp.status_code == 404


class TestLastRun:
    async def test_last_run_returns_null_per_type_when_no_jobs(self, client):
        resp = await client.get("/api/operations/last-run")
        assert resp.status_code == 200
        data = resp.json()
        assert data["FETCH"] is None
        assert data["SCORE"] is None
        assert data["RESCORE"] is None
        assert data["EXPORT"] is None


class TestConflictPrevention:
    @patch("app.routers.operations.run_fetch_job", new_callable=AsyncMock)
    async def test_fetch_rejects_when_fetch_running(self, mock_run, client, db, make_job):
        await make_job(
            job_type=JobType.FETCH, status=JobStatus.RUNNING
        )
        await db.commit()
        resp = await client.post("/api/operations/fetch")
        assert resp.status_code == 409

    @patch("app.routers.operations.run_score_job", new_callable=AsyncMock)
    async def test_score_rejects_when_score_or_rescore_running(
        self, mock_run, client, db, make_job
    ):
        await make_job(
            job_type=JobType.SCORE, status=JobStatus.RUNNING
        )
        await db.commit()
        resp = await client.post("/api/operations/score")
        assert resp.status_code == 409


class TestJobResponseShape:
    async def test_jobs_include_result_summary_and_timestamps(
        self, client, db, make_job
    ):
        from datetime import datetime, timezone

        job = await make_job(
            job_type=JobType.FETCH,
            status=JobStatus.COMPLETED,
            started_at=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            completed_at=datetime(2025, 1, 1, 12, 5, tzinfo=timezone.utc),
            result_summary={"fetched": 50, "scored": 45},
        )
        await db.commit()

        resp = await client.get("/api/operations/jobs")
        assert resp.status_code == 200
        jobs = resp.json()
        matching = [j for j in jobs if j["job_id"] == job.job_id]
        assert len(matching) == 1
        data = matching[0]
        assert data["result_summary"] == {"fetched": 50, "scored": 45}
        assert data["started_at"] is not None
        assert data["completed_at"] is not None

    async def test_failed_jobs_include_error_message(
        self, client, db, make_job
    ):
        job = await make_job(
            job_type=JobType.SCORE,
            status=JobStatus.FAILED,
            error_message="Claude API rate limited",
        )
        await db.commit()

        resp = await client.get(f"/api/operations/jobs/{job.job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error_message"] == "Claude API rate limited"


class TestFallbackToBackgroundTasks:
    @patch("app.routers.operations.run_fetch_job", new_callable=AsyncMock)
    async def test_falls_back_to_background_tasks_when_redis_unavailable(
        self, mock_run, client
    ):
        assert not redis_available()
        resp = await client.post("/api/operations/fetch")
        assert resp.status_code == 202
        mock_run.assert_called_once()


class TestRedisValidation:
    @patch("app.routers.operations.validate_redis")
    async def test_returns_503_when_redis_configured_but_unreachable(
        self, mock_validate, client
    ):
        mock_validate.return_value = "Redis is not reachable"
        resp = await client.post("/api/operations/fetch")
        assert resp.status_code == 503
        assert "Redis" in resp.json()["detail"]

    @patch("app.routers.operations.validate_redis")
    async def test_returns_503_for_all_operation_types(
        self, mock_validate, client
    ):
        mock_validate.return_value = "No workers listening"
        for op in ["fetch", "score", "rescore", "export"]:
            resp = await client.post(f"/api/operations/{op}")
            assert resp.status_code == 503, f"{op} should return 503"

    @patch("app.routers.operations.validate_redis")
    async def test_no_job_created_when_redis_validation_fails(
        self, mock_validate, client
    ):
        mock_validate.return_value = "Redis is not reachable"
        await client.post("/api/operations/fetch")
        resp = await client.get("/api/operations/jobs")
        assert resp.json() == []


class TestFetchWithParams:
    @patch("app.routers.operations.run_fetch_job", new_callable=AsyncMock)
    async def test_fetch_no_body_still_works(self, mock_run, client):
        resp = await client.post("/api/operations/fetch")
        assert resp.status_code == 202
        assert "job_id" in resp.json()

    @patch("app.routers.operations.run_fetch_job", new_callable=AsyncMock)
    async def test_fetch_with_full_json_body(self, mock_run, client, db):
        resp = await client.post(
            "/api/operations/fetch",
            json={"start_date": "2024-01-01", "end_date": "2024-01-31", "max_count": 50},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        result = await db.execute(select(Job).where(Job.job_id == job_id))
        job = result.scalar_one()
        assert job.result_summary is not None
        params = job.result_summary["params"]
        assert params["start_date"] == "2024-01-01"
        assert params["end_date"] == "2024-01-31"
        assert params["max_count"] == 50

    @patch("app.routers.operations.run_fetch_job", new_callable=AsyncMock)
    async def test_fetch_with_partial_body(self, mock_run, client, db):
        resp = await client.post(
            "/api/operations/fetch",
            json={"max_count": 25},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        result = await db.execute(select(Job).where(Job.job_id == job_id))
        job = result.scalar_one()
        params = job.result_summary["params"]
        assert params["start_date"] is None
        assert params["end_date"] is None
        assert params["max_count"] == 25

    @patch("app.routers.operations.run_fetch_job", new_callable=AsyncMock)
    async def test_fetch_params_stored_in_result_summary(self, mock_run, client, db):
        resp = await client.post(
            "/api/operations/fetch",
            json={"start_date": "2024-06-15"},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        result = await db.execute(select(Job).where(Job.job_id == job_id))
        job = result.scalar_one()
        assert "params" in job.result_summary
        assert job.result_summary["params"]["start_date"] == "2024-06-15"

    @patch("app.routers.operations.run_fetch_job", new_callable=AsyncMock)
    async def test_fetch_passes_params_to_run_fetch_job(self, mock_run, client):
        await client.post(
            "/api/operations/fetch",
            json={"start_date": "2024-01-01", "end_date": "2024-01-31", "max_count": 50},
        )
        _, kwargs = mock_run.call_args
        assert kwargs["fetch_start_date"].isoformat() == "2024-01-01"
        assert kwargs["fetch_end_date"].isoformat() == "2024-01-31"
        assert kwargs["max_count"] == 50


class TestJobExecutionIntegration:
    """End-to-end tests that let the job runner actually execute via BackgroundTasks.

    No mocking of the job runner itself — only external services (HubSpot, Claude)
    are mocked. Verifies the full path: endpoint → BackgroundTasks → _session_scope(None)
    → job runner → commit.
    """

    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock, return_value=3)
    @patch("app.services.job_runner.AsyncSessionLocal", TestingSessionLocal)
    async def test_fetch_job_completes_via_background_task(self, mock_fetch, client, db):
        await db.execute(
            select(Job)  # ensure settings seeded
        )
        resp = await client.post("/api/operations/fetch")
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        result = await db.execute(select(Job).where(Job.job_id == job_id))
        job = result.scalar_one()
        assert job.status == JobStatus.COMPLETED
        assert job.result_summary["fetched"] == 3
        assert job.started_at is not None
        assert job.completed_at is not None

    @patch("app.services.job_runner.score_unscored_emails", new_callable=AsyncMock)
    @patch("app.services.job_runner.AsyncSessionLocal", TestingSessionLocal)
    async def test_score_job_completes_via_background_task(self, mock_score, client, db):
        mock_score.return_value = {
            "scored": 5, "auto_scored": 0, "errors": 0,
            "total_input_tokens": 100, "total_output_tokens": 50,
        }
        resp = await client.post("/api/operations/score")
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        result = await db.execute(select(Job).where(Job.job_id == job_id))
        job = result.scalar_one()
        assert job.status == JobStatus.COMPLETED
        assert job.result_summary["scored"] == 5

    @patch("app.services.job_runner.export_to_excel", new_callable=AsyncMock, return_value="/tmp/export.xlsx")
    @patch("app.services.job_runner.AsyncSessionLocal", TestingSessionLocal)
    async def test_export_job_completes_via_background_task(self, mock_export, client, db):
        resp = await client.post("/api/operations/export")
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        result = await db.execute(select(Job).where(Job.job_id == job_id))
        job = result.scalar_one()
        assert job.status == JobStatus.COMPLETED
        assert job.result_summary["output_path"] == "/tmp/export.xlsx"

    @patch("app.services.job_runner.fetch_and_store", new_callable=AsyncMock)
    @patch("app.services.job_runner.AsyncSessionLocal", TestingSessionLocal)
    async def test_failed_job_persists_error_via_background_task(self, mock_fetch, client, db):
        mock_fetch.side_effect = RuntimeError("HubSpot API key invalid")
        resp = await client.post("/api/operations/fetch")
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        result = await db.execute(select(Job).where(Job.job_id == job_id))
        job = result.scalar_one()
        assert job.status == JobStatus.FAILED
        assert "HubSpot API key invalid" in job.error_message

    @patch("app.services.job_runner.score_unscored_emails", new_callable=AsyncMock)
    @patch("app.services.job_runner.AsyncSessionLocal", TestingSessionLocal)
    async def test_rescore_job_completes_via_background_task(self, mock_score, client, db):
        mock_score.return_value = {
            "scored": 2, "auto_scored": 0, "errors": 0,
            "total_input_tokens": 0, "total_output_tokens": 0,
        }
        resp = await client.post("/api/operations/rescore")
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        result = await db.execute(select(Job).where(Job.job_id == job_id))
        job = result.scalar_one()
        assert job.status == JobStatus.COMPLETED
