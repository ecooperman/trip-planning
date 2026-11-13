"""add cached images

Revision ID: e3ae3d39f355
Revises: a7d2c9e4b815
Create Date: 2026-11-13 14:38:46.453167

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3ae3d39f355'
down_revision: Union[str, Sequence[str], None] = 'a7d2c9e4b815'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('cached_images',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('content_type', sa.String(), nullable=False),
    sa.Column('data', sa.LargeBinary(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('cached_images')
