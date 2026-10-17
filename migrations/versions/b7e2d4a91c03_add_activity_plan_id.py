"""add activity plan_id (link to a social-planning plan)

Revision ID: b7e2d4a91c03
Revises: c4b1a7d9e620
Create Date: 2026-10-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2d4a91c03'
down_revision: Union[str, Sequence[str], None] = 'c4b1a7d9e620'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("activities") as batch_op:
        batch_op.add_column(sa.Column("plan_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_activities_plan_id", ["plan_id"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("activities") as batch_op:
        batch_op.drop_index("ix_activities_plan_id")
        batch_op.drop_column("plan_id")
