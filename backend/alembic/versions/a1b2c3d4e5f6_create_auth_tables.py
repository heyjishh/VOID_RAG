"""create auth tables (users, auth_sessions, otp_codes)

Revision ID: a1b2c3d4e5f6
Revises: 2aa66ded6410
Create Date: 2026-08-14 10:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '2aa66ded6410'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute('CREATE SCHEMA IF NOT EXISTS "juryai"')
    op.create_table('users',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('name', sa.String(length=160), server_default=sa.text("''"), nullable=False),
    sa.Column('org', sa.String(length=160), server_default=sa.text("''"), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=True),
    sa.Column('email_verified', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('phone_verified', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    schema='juryai'
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True, schema='juryai')
    op.create_index('ix_users_phone', 'users', ['phone'], unique=True, schema='juryai')
    op.create_index('ix_users_created_at', 'users', ['created_at'], unique=False, schema='juryai')

    op.create_table('auth_sessions',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('token', sa.String(length=64), nullable=False),
    sa.Column('revoked', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    schema='juryai'
    )
    op.create_index('ix_auth_sessions_token', 'auth_sessions', ['token'], unique=True, schema='juryai')
    op.create_index('ix_auth_sessions_user_id', 'auth_sessions', ['user_id'], unique=False, schema='juryai')

    op.create_table('otp_codes',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('purpose', sa.String(length=20), nullable=False),
    sa.Column('channel', sa.String(length=10), nullable=False),
    sa.Column('target', sa.String(length=320), nullable=False),
    sa.Column('code_hash', sa.String(length=128), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('consumed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    schema='juryai'
    )
    op.create_index('ix_otp_codes_target_purpose', 'otp_codes', ['target', 'purpose'], unique=False, schema='juryai')
    op.create_index('ix_otp_codes_created_at', 'otp_codes', ['created_at'], unique=False, schema='juryai')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_otp_codes_created_at', table_name='otp_codes', schema='juryai')
    op.drop_index('ix_otp_codes_target_purpose', table_name='otp_codes', schema='juryai')
    op.drop_table('otp_codes', schema='juryai')
    op.drop_index('ix_auth_sessions_user_id', table_name='auth_sessions', schema='juryai')
    op.drop_index('ix_auth_sessions_token', table_name='auth_sessions', schema='juryai')
    op.drop_table('auth_sessions', schema='juryai')
    op.drop_index('ix_users_created_at', table_name='users', schema='juryai')
    op.drop_index('ix_users_phone', table_name='users', schema='juryai')
    op.drop_index('ix_users_email', table_name='users', schema='juryai')
    op.drop_table('users', schema='juryai')