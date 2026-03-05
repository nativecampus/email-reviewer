import math
from datetime import date, datetime

import pytest

from app.services.rep import get_rep_emails, get_team


async def _make_scored_rep(make_rep, make_email, make_score, email, name, count=1):
    """Create a rep with `count` scored emails."""
    rep = await make_rep(email=email, display_name=name)
    for i in range(count):
        em = await make_email(from_email=email, subject=f"Email {i}")
        await make_score(email_id=em.id, overall=7)
    return rep


class TestGetTeamPagination:
    async def test_returns_paginated_dict_keys(self, db, make_rep, make_email, make_score):
        await _make_scored_rep(make_rep, make_email, make_score, "a@x.com", "A")
        result = await get_team(db)
        assert set(result.keys()) == {"items", "total", "page", "per_page", "pages"}

    async def test_default_pagination(self, db, make_rep, make_email, make_score):
        for i in range(3):
            await _make_scored_rep(make_rep, make_email, make_score, f"r{i}@x.com", f"R{i}")
        result = await get_team(db)
        assert result["page"] == 1
        assert result["per_page"] == 20
        assert result["total"] == 3
        assert len(result["items"]) == 3
        assert result["pages"] == 1

    async def test_page_2_returns_correct_slice(self, db, make_rep, make_email, make_score):
        for i in range(25):
            await _make_scored_rep(
                make_rep, make_email, make_score, f"r{i:03d}@x.com", f"R{i:03d}"
            )
        page1 = await get_team(db, page=1, per_page=20)
        page2 = await get_team(db, page=2, per_page=20)
        assert len(page1["items"]) == 20
        assert len(page2["items"]) == 5
        assert page2["page"] == 2
        # No overlap between pages
        emails_p1 = {r.email for r in page1["items"]}
        emails_p2 = {r.email for r in page2["items"]}
        assert emails_p1.isdisjoint(emails_p2)

    async def test_per_page_none_returns_all(self, db, make_rep, make_email, make_score):
        for i in range(25):
            await _make_scored_rep(
                make_rep, make_email, make_score, f"r{i:03d}@x.com", f"R{i:03d}"
            )
        result = await get_team(db, per_page=None)
        assert len(result["items"]) == 25
        assert result["total"] == 25
        assert result["per_page"] is None
        assert result["pages"] == 1

    async def test_per_page_zero_returns_all(self, db, make_rep, make_email, make_score):
        for i in range(5):
            await _make_scored_rep(
                make_rep, make_email, make_score, f"r{i}@x.com", f"R{i}"
            )
        result = await get_team(db, per_page=0)
        assert len(result["items"]) == 5

    async def test_pages_computed_correctly(self, db, make_rep, make_email, make_score):
        for i in range(25):
            await _make_scored_rep(
                make_rep, make_email, make_score, f"r{i:03d}@x.com", f"R{i:03d}"
            )
        result = await get_team(db, per_page=20)
        assert result["pages"] == 2

    async def test_out_of_range_page_returns_empty(self, db, make_rep, make_email, make_score):
        for i in range(3):
            await _make_scored_rep(make_rep, make_email, make_score, f"r{i}@x.com", f"R{i}")
        result = await get_team(db, page=99)
        assert result["items"] == []
        assert result["total"] == 3


class TestGetRepEmailsPagination:
    async def _seed_emails(self, make_rep, make_email, make_score, count=25):
        rep = await make_rep(email="rep@x.com", display_name="Rep")
        for i in range(count):
            em = await make_email(from_email="rep@x.com", subject=f"Email {i}")
            await make_score(email_id=em.id, overall=5 + (i % 5))
        return rep

    async def test_returns_paginated_dict_keys(self, db, make_rep, make_email, make_score):
        await self._seed_emails(make_rep, make_email, make_score, count=1)
        result = await get_rep_emails(db, "rep@x.com")
        assert set(result.keys()) == {"items", "total", "page", "per_page", "pages"}

    async def test_default_pagination(self, db, make_rep, make_email, make_score):
        await self._seed_emails(make_rep, make_email, make_score, count=5)
        result = await get_rep_emails(db, "rep@x.com")
        assert result["page"] == 1
        assert result["per_page"] == 20
        assert result["total"] == 5
        assert len(result["items"]) == 5
        assert result["pages"] == 1

    async def test_page_boundaries(self, db, make_rep, make_email, make_score):
        await self._seed_emails(make_rep, make_email, make_score, count=25)
        page1 = await get_rep_emails(db, "rep@x.com", page=1, per_page=20)
        page2 = await get_rep_emails(db, "rep@x.com", page=2, per_page=20)
        assert len(page1["items"]) == 20
        assert len(page2["items"]) == 5
        assert page2["page"] == 2
        assert page2["pages"] == 2
        # No overlap
        ids_p1 = {e.id for e in page1["items"]}
        ids_p2 = {e.id for e in page2["items"]}
        assert ids_p1.isdisjoint(ids_p2)

    async def test_per_page_none_returns_all(self, db, make_rep, make_email, make_score):
        await self._seed_emails(make_rep, make_email, make_score, count=25)
        result = await get_rep_emails(db, "rep@x.com", per_page=None)
        assert len(result["items"]) == 25
        assert result["total"] == 25
        assert result["per_page"] is None
        assert result["pages"] == 1


class TestGetRepEmailsFilters:
    """Tests for search and filter parameters on get_rep_emails()."""

    async def test_search_filters_by_subject(self, db, make_rep, make_email, make_score):
        await make_rep(email="rep@x.com", display_name="Rep")
        e1 = await make_email(from_email="rep@x.com", subject="Quarterly review")
        await make_score(email_id=e1.id)
        e2 = await make_email(from_email="rep@x.com", subject="Hello there")
        await make_score(email_id=e2.id)

        result = await get_rep_emails(db, "rep@x.com", search="quarterly")
        assert result["total"] == 1
        assert result["items"][0].subject == "Quarterly review"

    async def test_search_filters_by_body_text(self, db, make_rep, make_email, make_score):
        await make_rep(email="rep@x.com", display_name="Rep")
        e1 = await make_email(
            from_email="rep@x.com", subject="A", body_text="Meeting about budget"
        )
        await make_score(email_id=e1.id)
        e2 = await make_email(
            from_email="rep@x.com", subject="B", body_text="General greeting"
        )
        await make_score(email_id=e2.id)

        result = await get_rep_emails(db, "rep@x.com", search="budget")
        assert result["total"] == 1
        assert result["items"][0].body_text == "Meeting about budget"

    async def test_date_from_filters_emails(self, db, make_rep, make_email, make_score):
        await make_rep(email="rep@x.com", display_name="Rep")
        e1 = await make_email(
            from_email="rep@x.com", subject="Old",
            timestamp=datetime(2024, 1, 1),
        )
        await make_score(email_id=e1.id)
        e2 = await make_email(
            from_email="rep@x.com", subject="New",
            timestamp=datetime(2024, 6, 15),
        )
        await make_score(email_id=e2.id)

        result = await get_rep_emails(
            db, "rep@x.com", date_from=date(2024, 3, 1)
        )
        assert result["total"] == 1
        assert result["items"][0].subject == "New"

    async def test_date_to_filters_emails(self, db, make_rep, make_email, make_score):
        await make_rep(email="rep@x.com", display_name="Rep")
        e1 = await make_email(
            from_email="rep@x.com", subject="Old",
            timestamp=datetime(2024, 1, 1),
        )
        await make_score(email_id=e1.id)
        e2 = await make_email(
            from_email="rep@x.com", subject="New",
            timestamp=datetime(2024, 6, 15),
        )
        await make_score(email_id=e2.id)

        result = await get_rep_emails(
            db, "rep@x.com", date_to=date(2024, 3, 1)
        )
        assert result["total"] == 1
        assert result["items"][0].subject == "Old"

    async def test_score_min_filters_emails(self, db, make_rep, make_email, make_score):
        await make_rep(email="rep@x.com", display_name="Rep")
        e1 = await make_email(from_email="rep@x.com", subject="Low")
        await make_score(email_id=e1.id, overall=3)
        e2 = await make_email(from_email="rep@x.com", subject="High")
        await make_score(email_id=e2.id, overall=8)

        result = await get_rep_emails(db, "rep@x.com", score_min=5)
        assert result["total"] == 1
        assert result["items"][0].subject == "High"

    async def test_score_max_filters_emails(self, db, make_rep, make_email, make_score):
        await make_rep(email="rep@x.com", display_name="Rep")
        e1 = await make_email(from_email="rep@x.com", subject="Low")
        await make_score(email_id=e1.id, overall=3)
        e2 = await make_email(from_email="rep@x.com", subject="High")
        await make_score(email_id=e2.id, overall=8)

        result = await get_rep_emails(db, "rep@x.com", score_max=5)
        assert result["total"] == 1
        assert result["items"][0].subject == "Low"

    async def test_combined_filters(self, db, make_rep, make_email, make_score):
        await make_rep(email="rep@x.com", display_name="Rep")
        # Matches search + date + score
        e1 = await make_email(
            from_email="rep@x.com", subject="Quarterly review",
            timestamp=datetime(2024, 6, 1),
        )
        await make_score(email_id=e1.id, overall=8)
        # Matches search + date but not score
        e2 = await make_email(
            from_email="rep@x.com", subject="Quarterly update",
            timestamp=datetime(2024, 7, 1),
        )
        await make_score(email_id=e2.id, overall=2)
        # Matches date + score but not search
        e3 = await make_email(
            from_email="rep@x.com", subject="Hello",
            timestamp=datetime(2024, 5, 1),
        )
        await make_score(email_id=e3.id, overall=9)

        result = await get_rep_emails(
            db, "rep@x.com",
            search="quarterly",
            date_from=date(2024, 1, 1),
            score_min=5,
        )
        assert result["total"] == 1
        assert result["items"][0].subject == "Quarterly review"

    async def test_pagination_with_filters(self, db, make_rep, make_email, make_score):
        await make_rep(email="rep@x.com", display_name="Rep")
        for i in range(5):
            e = await make_email(
                from_email="rep@x.com", subject=f"Match {i}",
                timestamp=datetime(2024, 6, i + 1),
            )
            await make_score(email_id=e.id, overall=8)
        # Non-matching emails
        for i in range(3):
            e = await make_email(
                from_email="rep@x.com", subject=f"Other {i}",
                timestamp=datetime(2024, 6, i + 1),
            )
            await make_score(email_id=e.id, overall=2)

        result = await get_rep_emails(
            db, "rep@x.com", score_min=5, page=1, per_page=3
        )
        assert result["total"] == 5
        assert len(result["items"]) == 3
        assert result["pages"] == 2

        page2 = await get_rep_emails(
            db, "rep@x.com", score_min=5, page=2, per_page=3
        )
        assert len(page2["items"]) == 2
