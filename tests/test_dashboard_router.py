import pytest


class TestTeamPage:
    async def test_get_root_returns_200(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200

    async def test_get_root_contains_team(self, client):
        resp = await client.get("/")
        assert "Team" in resp.text


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
