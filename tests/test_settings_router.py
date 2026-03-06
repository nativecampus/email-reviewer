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


class TestPatchWeights:
    async def test_updates_weight_value_proposition(self, client):
        resp = await client.patch(
            "/api/settings",
            json={
                "weight_value_proposition": 0.25,
                "weight_personalisation": 0.25,
                "weight_cta": 0.25,
                "weight_clarity": 0.25,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["weight_value_proposition"] == 0.25

    async def test_rejects_weights_not_summing_to_one(self, client):
        resp = await client.patch(
            "/api/settings",
            json={
                "weight_value_proposition": 0.50,
                "weight_personalisation": 0.30,
                "weight_cta": 0.20,
                "weight_clarity": 0.15,
            },
        )
        assert resp.status_code == 422

    async def test_accepts_weights_summing_to_one(self, client):
        resp = await client.patch(
            "/api/settings",
            json={
                "weight_value_proposition": 0.40,
                "weight_personalisation": 0.30,
                "weight_cta": 0.20,
                "weight_clarity": 0.10,
            },
        )
        assert resp.status_code == 200


class TestPatchPrompts:
    async def test_updates_initial_email_prompt(self, client):
        resp = await client.patch(
            "/api/settings",
            json={"initial_email_prompt": "New prompt text"},
        )
        assert resp.status_code == 200
        assert resp.json()["initial_email_prompt"] == "New prompt text"

    async def test_rejects_empty_initial_email_prompt(self, client):
        resp = await client.patch(
            "/api/settings",
            json={"initial_email_prompt": ""},
        )
        assert resp.status_code == 422


class TestGetSettingsNewFields:
    async def test_response_includes_new_fields_with_defaults(self, client):
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["weight_value_proposition"] == 0.35
        assert data["weight_personalisation"] == 0.30
        assert data["weight_cta"] == 0.20
        assert data["weight_clarity"] == 0.15


class TestSettingsPage:
    async def test_returns_200_html(self, client):
        resp = await client.get("/settings")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_dev_mode_section_visible_when_auth_disabled(self, client):
        resp = await client.get("/settings")
        assert resp.status_code == 200
        assert "Dev Mode" in resp.text

    async def test_dev_mode_contains_form_elements(self, client):
        resp = await client.get("/settings")
        html = resp.text
        assert 'id="fetch_start_date"' in html
        assert 'id="fetch_end_date"' in html
        assert 'id="fetch_max_count"' in html
        assert "Fetch Start Date" in html
        assert "Fetch End Date" in html
        assert "Max Emails" in html
