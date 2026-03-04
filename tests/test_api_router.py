import pytest


class TestGetReps:
    async def test_returns_200_with_empty_list(self, client):
        resp = await client.get("/api/reps")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_rep_objects_with_avg_score_fields(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@example.com", display_name="Rep One")
        email = await make_email(from_email="rep@example.com")
        await make_score(email_id=email.id, overall=8, clarity=9)

        resp = await client.get("/api/reps")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        row = data[0]
        assert row["email"] == "rep@example.com"
        assert row["avg_overall"] is not None
        assert row["avg_clarity"] is not None
        assert row["avg_personalisation"] is not None
        assert row["avg_value_proposition"] is not None
        assert row["avg_cta"] is not None

    async def test_results_sorted_by_overall_avg_descending(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="low@example.com", display_name="Low Rep")
        email_low = await make_email(from_email="low@example.com")
        await make_score(email_id=email_low.id, overall=3)

        await make_rep(email="high@example.com", display_name="High Rep")
        email_high = await make_email(from_email="high@example.com")
        await make_score(email_id=email_high.id, overall=9)

        resp = await client.get("/api/reps")
        data = resp.json()
        assert len(data) == 2
        assert data[0]["email"] == "high@example.com"
        assert data[1]["email"] == "low@example.com"


class TestGetRepEmails:
    async def test_returns_scored_emails_for_rep(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@example.com", display_name="Rep")
        email = await make_email(
            from_email="rep@example.com", subject="Follow up"
        )
        await make_score(email_id=email.id, overall=7)

        resp = await client.get("/api/reps/rep@example.com/emails")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["subject"] == "Follow up"

    async def test_returns_empty_list_for_unknown_rep(self, client):
        resp = await client.get("/api/reps/nobody@example.com/emails")
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetEmailDetail:
    async def test_returns_email_with_score(
        self, client, make_email, make_score
    ):
        email = await make_email(
            from_email="rep@example.com", subject="Hello"
        )
        await make_score(email_id=email.id, overall=8)

        resp = await client.get(f"/api/emails/{email.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == email.id
        assert data["subject"] == "Hello"
        assert data["score"]["overall"] == 8

    async def test_returns_404_for_nonexistent_id(self, client):
        resp = await client.get("/api/emails/99999")
        assert resp.status_code == 404


class TestGetStats:
    async def test_returns_correct_totals(
        self, client, make_rep, make_email, make_score
    ):
        await make_rep(email="rep@example.com", display_name="Rep")
        e1 = await make_email(from_email="rep@example.com")
        e2 = await make_email(from_email="rep@example.com")
        await make_score(email_id=e1.id, overall=6)
        # e2 has no score

        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_emails"] == 2
        assert data["total_scored"] == 1
        assert data["total_reps"] == 1

    async def test_returns_zeros_when_empty(self, client):
        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_emails"] == 0
        assert data["total_scored"] == 0
        assert data["total_reps"] == 0
