"""create draft_run table

Revision ID: b7f3c9d1e2a4
Revises: a1b2c3d4e5f6
Create Date: 2026-08-18 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b7f3c9d1e2a4'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute('CREATE SCHEMA IF NOT EXISTS "juryai"')
    op.create_table(
        'draft_run',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=200), server_default=sa.text("''"), nullable=False),
        sa.Column('document_type', sa.String(length=40), server_default=sa.text("''"), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('brief', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column('status', sa.String(length=20), server_default=sa.text("'completed'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['juryai.users.id']),
        schema='juryai',
    )
    op.create_index('ix_draft_run_user_id', 'draft_run', ['user_id'], schema='juryai')
    op.create_index('ix_draft_run_created_at', 'draft_run', ['created_at'], schema='juryai')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_draft_run_created_at', table_name='draft_run', schema='juryai')
    op.drop_index('ix_draft_run_user_id', table_name='draft_run', schema='juryai')
    op.drop_table('draft_run', schema='juryai')
