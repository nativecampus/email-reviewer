import pytest


class TestTeamPage:
    async def test_get_root_returns_200(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200

    async def test_get_root_contains_team(self, client):
        resp = await client.get("/")
        assert "Team" in resp.text

    async def test_get_root_accepts_pagination_params(
        self, client, make_rep, make_email, make_score
    ):
        for i in range(25):
            rep = await make_rep(email=f"r{i:03d}@x.com", display_name=f"Rep {i:03d}")
            em = await make_email(from_email=rep.email, subject=f"Subj {i}")
            await make_score(email_id=em.id, overall=7)
        resp = await client.get("/", params={"page": 2, "per_page": 20})
        assert resp.status_code == 200
        # Page 2 should show 5 reps (25 total, 20 per page)
        assert "Page 2 of 2" in resp.text

    async def test_get_root_default_pagination(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200


class TestRepDetailPage:
    async def test_get_rep_detail_returns_200_when_rep_exists(
        self, client, make_rep
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        resp = await client.get("/reps/alice@example.com")
        assert resp.status_code == 200

    async def test_get_rep_detail_returns_404_when_rep_missing(self, client):
        resp = await client.get("/reps/nobody@example.com")
        assert resp.status_code == 404

    async def test_get_rep_detail_accepts_pagination_params(
        self, client, make_rep, make_email, make_score
    ):
        rep = await make_rep(email="alice@example.com", display_name="Alice")
        for i in range(5):
            em = await make_email(from_email="alice@example.com", subject=f"Subj {i}")
            await make_score(email_id=em.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com", params={"page": 1, "per_page": 20}
        )
        assert resp.status_code == 200

    async def test_search_filter_returns_200(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Hello world")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com", params={"search": "hello"}
        )
        assert resp.status_code == 200

    async def test_date_and_score_filters_return_200(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Test")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com",
            params={"date_from": "2024-01-01", "score_min": "5"},
        )
        assert resp.status_code == 200


class TestRepExport:
    async def test_export_filtered_returns_xlsx(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Hello world")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com/export",
            params={"export_all": "false", "search": "hello"},
        )
        assert resp.status_code == 200
        assert (
            resp.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    async def test_export_all_returns_xlsx(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="alice@example.com", display_name="Alice")
        e = await make_email(from_email="alice@example.com", subject="Test")
        await make_score(email_id=e.id, overall=7)
        resp = await client.get(
            "/reps/alice@example.com/export",
            params={"export_all": "true"},
        )
        assert resp.status_code == 200
        assert (
            resp.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
