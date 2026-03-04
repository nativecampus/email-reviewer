from unittest.mock import AsyncMock, patch

from app.enums import JobStatus, JobType


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
