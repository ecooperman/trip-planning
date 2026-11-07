"""add invites

Requests to let someone who has no account yet in: a trip's owner asks, an
administrator approves or declines (see app/routers/invites.py).

Revision ID: d4f7a2c9b815
Revises: c3d8e5a21f74
Create Date: 2026-11-06 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f7a2c9b815'
down_revision: Union[str, Sequence[str], None] = 'c3d8e5a21f74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("invited_by_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"]),
        sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", "email", name="uq_invites_trip_id_email"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("invites")
