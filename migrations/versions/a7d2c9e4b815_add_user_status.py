"""add status to users

Each person is "active" (enabled in this app) or "removed" (revoked by the
administrator). Everyone who has an account today is enabled, so existing rows
become active; from now on an account is only created for someone the
administrator let in, so the app no longer opens up to anyone who merely passes
the login gate.

Revision ID: a7d2c9e4b815
Revises: f6b9d2a41c70
Create Date: 2026-11-11 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d2c9e4b815'
down_revision: Union[str, Sequence[str], None] = 'f6b9d2a41c70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default so the NOT NULL column can be added to existing rows.
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(), nullable=False, server_default="active"))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("status")
