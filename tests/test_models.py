from sqlalchemy import select

from app.models.base import Base
from app.models.chain import EmailChain
from app.models.chain_score import ChainScore
from app.models.email import Email
from app.models.score import Score


class TestTableRegistration:
    def test_all_tables_registered(self):
        table_names = set(Base.metadata.tables.keys())
        assert len(table_names) == 7
        assert table_names == {
            "emails",
            "scores",
            "reps",
            "settings",
            "jobs",
            "email_chains",
            "chain_scores",
        }


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

    def test_chain_columns(self):
        column_names = {c.name for c in Email.__table__.columns}
        chain_columns = {
            "chain_id",
            "position_in_chain",
            "open_count",
            "click_count",
            "reply_count",
            "message_id",
            "in_reply_to",
            "thread_id",
        }
        assert chain_columns <= column_names


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


class TestEmailChainsTableColumns:
    def test_expected_columns(self):
        column_names = {c.name for c in EmailChain.__table__.columns}
        expected = {
            "id",
            "normalized_subject",
            "participants",
            "started_at",
            "last_activity_at",
            "email_count",
            "outgoing_count",
            "incoming_count",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        }
        assert expected <= column_names


class TestChainScoresTableColumns:
    def test_expected_columns(self):
        column_names = {c.name for c in ChainScore.__table__.columns}
        expected = {
            "id",
            "chain_id",
            "progression",
            "responsiveness",
            "persistence",
            "conversation_quality",
            "avg_response_hours",
            "notes",
            "score_error",
            "scored_at",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        }
        assert expected <= column_names


class TestSettingsTableColumns:
    def test_new_columns(self):
        from app.models.settings import Settings

        column_names = {c.name for c in Settings.__table__.columns}
        new_columns = {
            "initial_email_prompt",
            "chain_email_prompt",
            "chain_evaluation_prompt",
            "weight_value_proposition",
            "weight_personalisation",
            "weight_cta",
            "weight_clarity",
        }
        assert new_columns <= column_names


class TestEmailChainEmailRelationship:
    async def test_one_to_many(self, db, make_chain, make_email):
        chain = await make_chain()
        email1 = await make_email(chain_id=chain.id, position_in_chain=1)
        email2 = await make_email(chain_id=chain.id, position_in_chain=2)

        result = await db.execute(
            select(EmailChain).where(EmailChain.id == chain.id)
        )
        loaded_chain = result.scalar_one()
        await db.refresh(loaded_chain, ["emails"])
        email_ids = {e.id for e in loaded_chain.emails}
        assert email_ids == {email1.id, email2.id}


class TestEmailChainChainScoreRelationship:
    async def test_one_to_one(self, db, make_chain, make_chain_score):
        chain = await make_chain()
        chain_score = await make_chain_score(chain_id=chain.id)

        result = await db.execute(
            select(EmailChain).where(EmailChain.id == chain.id)
        )
        loaded_chain = result.scalar_one()
        await db.refresh(loaded_chain, ["chain_score"])
        assert loaded_chain.chain_score.id == chain_score.id

    async def test_cascade_delete_removes_chain_score(self, db, make_chain, make_chain_score):
        chain = await make_chain()
        await make_chain_score(chain_id=chain.id)

        await db.delete(chain)
        await db.flush()

        result = await db.execute(select(ChainScore))
        assert result.scalars().all() == []


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
