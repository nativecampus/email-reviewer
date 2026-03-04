"""add settings and jobs tables

Revision ID: a3f1b2c4d5e6
Revises: 2ce1841a94ba
Create Date: 2026-03-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1b2c4d5e6'
down_revision: Union[str, None] = '2ce1841a94ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('global_start_date', sa.Date(), nullable=False),
        sa.Column('company_domains', sa.String(), nullable=False),
        sa.Column('scoring_batch_size', sa.Integer(), nullable=False),
        sa.Column('auto_score_after_fetch', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('updated_by', sa.String(), nullable=False),
        sa.CheckConstraint('id = 1', name='single_row_settings'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('jobs',
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('job_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('result_summary', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('triggered_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('updated_by', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('job_id')
    )

    # Seed default settings row
    op.execute(
        "INSERT INTO settings (id, global_start_date, company_domains, scoring_batch_size, "
        "auto_score_after_fetch, created_at, updated_at, created_by, updated_by) "
        "VALUES (1, '2025-09-01', 'nativecampusadvertising.com,native.fm', 5, "
        "true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'system', 'system')"
    )


def downgrade() -> None:
    op.drop_table('jobs')
    op.drop_table('settings')
