from datetime import datetime


class TestGetChainDetail:
    async def test_returns_200_with_chain_and_emails(
        self, client, make_chain, make_email, make_chain_score
    ):
        chain = await make_chain(
            normalized_subject="Project update",
            email_count=2,
            started_at=datetime(2025, 1, 1),
            last_activity_at=datetime(2025, 1, 3),
        )
        await make_email(
            from_email="alice@example.com",
            subject="Re: Project update",
            chain_id=chain.id,
            position_in_chain=1,
            timestamp=datetime(2025, 1, 1),
        )
        await make_email(
            from_email="bob@example.com",
            subject="Re: Project update",
            chain_id=chain.id,
            position_in_chain=2,
            timestamp=datetime(2025, 1, 3),
        )
        await make_chain_score(chain_id=chain.id, conversation_quality=7)

        resp = await client.get(f"/api/chains/{chain.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["normalized_subject"] == "Project update"
        assert len(data["emails"]) == 2
        # Emails in timestamp order
        assert data["emails"][0]["from_email"] == "alice@example.com"
        assert data["emails"][1]["from_email"] == "bob@example.com"
        assert data["chain_score"]["conversation_quality"] == 7

    async def test_returns_404_for_nonexistent_chain(self, client):
        resp = await client.get("/api/chains/99999")
        assert resp.status_code == 404


class TestGetRepChains:
    async def test_returns_chains_for_rep(
        self, client, make_chain, make_email
    ):
        chain = await make_chain(
            normalized_subject="Sales pitch",
            email_count=2,
        )
        await make_email(
            from_email="rep@example.com",
            subject="Sales pitch",
            chain_id=chain.id,
            position_in_chain=1,
        )

        resp = await client.get("/api/reps/rep@example.com/chains")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["normalized_subject"] == "Sales pitch"

    async def test_returns_empty_list_for_unknown_rep(self, client):
        resp = await client.get("/api/reps/nobody@example.com/chains")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
