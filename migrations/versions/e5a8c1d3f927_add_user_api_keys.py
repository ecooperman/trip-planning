"""add user api keys

A person's own keys for the paid services the app can call (Anthropic, Google
Maps, Jina), saved encrypted from their Profile page (see app/apikeys.py).

Revision ID: e5a8c1d3f927
Revises: d4f7a2c9b815
Create Date: 2026-11-07 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a8c1d3f927'
down_revision: Union[str, Sequence[str], None] = 'd4f7a2c9b815'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_api_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("last4", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_api_keys_user_id_provider"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("user_api_keys")
