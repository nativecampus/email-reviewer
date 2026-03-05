from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.enums import JobStatus, JobType
from app.models.job import Job
from app.worker import redis_available


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
