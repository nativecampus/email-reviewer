from sqlalchemy import select

from app.models.base import Base
from app.models.email import Email
from app.models.score import Score


class TestTableRegistration:
    def test_all_tables_registered(self):
        table_names = set(Base.metadata.tables.keys())
        assert table_names == {"emails", "scores", "reps"}


class TestEmailsTableColumns:
    def test_expected_columns(self):
        column_names = {c.name for c in Email.__table__.columns}
        expected = {
            "id",
            "created_at",
            "timestamp",
            "from_name",
            "from_email",
            "to_name",
            "to_email",
            "subject",
            "body_text",
            "direction",
            "hubspot_id",
            "fetched_at",
        }
        assert expected <= column_names


class TestScoresTableColumns:
    def test_expected_columns(self):
        column_names = {c.name for c in Score.__table__.columns}
        expected = {
            "id",
            "email_id",
            "personalisation",
            "clarity",
            "value_proposition",
            "cta",
            "overall",
            "notes",
            "score_error",
            "scored_at",
        }
        assert expected <= column_names


class TestRepsTableColumns:
    def test_expected_columns(self):
        from app.models.rep import Rep

        column_names = {c.name for c in Rep.__table__.columns}
        assert "email" in column_names
        assert "display_name" in column_names

    def test_email_is_primary_key(self):
        from app.models.rep import Rep

        pk_cols = [c.name for c in Rep.__table__.primary_key.columns]
        assert pk_cols == ["email"]


class TestEmailScoreRelationship:
    async def test_one_to_one(self, db, make_email, make_score):
        email = await make_email()
        score = await make_score(email_id=email.id)

        result = await db.execute(select(Email).where(Email.id == email.id))
        loaded_email = result.scalar_one()
        await db.refresh(loaded_email, ["score"])
        assert loaded_email.score.id == score.id

    async def test_cascade_delete(self, db, make_email, make_score):
        email = await make_email()
        await make_score(email_id=email.id)

        await db.delete(email)
        await db.flush()

        result = await db.execute(select(Score))
        assert result.scalars().all() == []


class TestAuditMixin:
    async def test_populates_created_by_and_updated_by_on_insert(
        self, db, make_email
    ):
        email = await make_email()
        assert email.created_by == "test"
        assert email.updated_by == "test"
