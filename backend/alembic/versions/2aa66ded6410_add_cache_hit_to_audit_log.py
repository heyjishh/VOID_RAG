"""add cache_hit to audit_log

Revision ID: 2aa66ded6410
Revises: 0949d00c6416
Create Date: 2026-08-11 15:55:31.723716

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2aa66ded6410'
down_revision: Union[str, Sequence[str], None] = '0949d00c6416'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default only for the backfill of existing rows; the ORM model has
    # no default= at the DB level so new inserts always supply the value explicitly.
    op.add_column(
        'audit_log',
        sa.Column('cache_hit', sa.Boolean(), nullable=False, server_default=sa.false()),
        schema='juryai',
    )
    op.alter_column('audit_log', 'cache_hit', server_default=None, schema='juryai')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('audit_log', 'cache_hit', schema='juryai')
