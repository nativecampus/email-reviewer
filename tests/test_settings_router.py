from datetime import date, timedelta


class TestGetSettings:
    async def test_returns_200_with_current_settings(self, client):
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "global_start_date" in data
        assert "company_domains" in data
        assert "scoring_batch_size" in data
        assert "auto_score_after_fetch" in data
        assert data["global_start_date"] == "2025-09-01"
        assert data["company_domains"] == "nativecampusadvertising.com,native.fm"
        assert data["scoring_batch_size"] == 5
        assert data["auto_score_after_fetch"] is True


class TestPatchSettings:
    async def test_updates_global_start_date(self, client):
        resp = await client.patch(
            "/api/settings", json={"global_start_date": "2025-06-01"}
        )
        assert resp.status_code == 200
        assert resp.json()["global_start_date"] == "2025-06-01"

    async def test_updates_company_domains(self, client):
        resp = await client.patch(
            "/api/settings", json={"company_domains": "acme.com,test.com"}
        )
        assert resp.status_code == 200
        assert resp.json()["company_domains"] == "acme.com,test.com"

    async def test_updates_scoring_batch_size(self, client):
        resp = await client.patch(
            "/api/settings", json={"scoring_batch_size": 10}
        )
        assert resp.status_code == 200
        assert resp.json()["scoring_batch_size"] == 10

    async def test_updates_auto_score_after_fetch(self, client):
        resp = await client.patch(
            "/api/settings", json={"auto_score_after_fetch": False}
        )
        assert resp.status_code == 200
        assert resp.json()["auto_score_after_fetch"] is False

    async def test_partial_update_leaves_other_fields_unchanged(self, client):
        resp = await client.patch(
            "/api/settings", json={"scoring_batch_size": 20}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scoring_batch_size"] == 20
        assert data["global_start_date"] == "2025-09-01"
        assert data["company_domains"] == "nativecampusadvertising.com,native.fm"
        assert data["auto_score_after_fetch"] is True

    async def test_rejects_future_global_start_date(self, client):
        future = (date.today() + timedelta(days=30)).isoformat()
        resp = await client.patch(
            "/api/settings", json={"global_start_date": future}
        )
        assert resp.status_code == 422

    async def test_rejects_empty_company_domains(self, client):
        resp = await client.patch(
            "/api/settings", json={"company_domains": "  "}
        )
        assert resp.status_code == 422

    async def test_rejects_scoring_batch_size_less_than_1(self, client):
        resp = await client.patch(
            "/api/settings", json={"scoring_batch_size": 0}
        )
        assert resp.status_code == 422


class TestSettingsPage:
    async def test_returns_200_html(self, client):
        resp = await client.get("/settings")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
