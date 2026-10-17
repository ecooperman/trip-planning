"""allow multiple categories per activity and place

Revision ID: 500ff36719bd
Revises: a6808b8e52b5
Create Date: 2026-09-08 13:42:05.847601

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '500ff36719bd'
down_revision: Union[str, Sequence[str], None] = 'a6808b8e52b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'activity_categories',
        sa.Column('activity_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], ),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('activity_id', 'category_id'),
    )
    op.create_table(
        'place_categories',
        sa.Column('place_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['place_id'], ['places.id'], ),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('place_id', 'category_id'),
    )

    # Backfill every existing single category assignment into the new join
    # tables before dropping the old columns - nothing here changes any
    # activity's/place's effective category, just how it's stored.
    op.execute("INSERT INTO activity_categories (activity_id, category_id) SELECT id, category_id FROM activities WHERE category_id IS NOT NULL")
    op.execute("INSERT INTO place_categories (place_id, category_id) SELECT id, category_id FROM places WHERE category_id IS NOT NULL")

    with op.batch_alter_table('activities', schema=None) as batch_op:
        batch_op.drop_column('category_id')
    with op.batch_alter_table('places', schema=None) as batch_op:
        batch_op.drop_column('category_id')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('places', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('activities', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category_id', sa.Integer(), nullable=True))

    # Best-effort restore - if anything actually ended up with more than
    # one category (the whole point of this migration), only one
    # arbitrarily survives the downgrade. Fine for a downgrade path; the
    # upgrade path never relies on this direction.
    op.execute("""
        UPDATE activities SET category_id = (
            SELECT category_id FROM activity_categories WHERE activity_id = activities.id LIMIT 1
        )
    """)
    op.execute("""
        UPDATE places SET category_id = (
            SELECT category_id FROM place_categories WHERE place_id = places.id LIMIT 1
        )
    """)

    op.drop_table('place_categories')
    op.drop_table('activity_categories')
