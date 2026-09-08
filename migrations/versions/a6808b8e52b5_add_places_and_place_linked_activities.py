"""add places and place-linked activities

Revision ID: a6808b8e52b5
Revises: d0c2c5684be4
Create Date: 2026-09-05 14:12:34.949933

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6808b8e52b5'
down_revision: Union[str, Sequence[str], None] = 'd0c2c5684be4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'places',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('address', sa.String(), nullable=True),
        sa.Column('city', sa.String(), nullable=True),
        sa.Column('phone_number', sa.String(), nullable=True),
        sa.Column('map_link', sa.String(), nullable=True),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('review', sa.Text(), nullable=True),
        sa.Column('scrape_status', sa.Enum('not_started', 'success', 'failed', 'unsupported', name='scrapestatus'), nullable=False),
        sa.Column('scraped_title', sa.String(), nullable=True),
        sa.Column('scraped_description', sa.String(), nullable=True),
        sa.Column('scraped_image_url', sa.String(), nullable=True),
        sa.Column('scraped_at', sa.DateTime(), nullable=True),
        sa.Column('scrape_error', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'place_images',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('place_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('content_type', sa.String(), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['place_id'], ['places.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # SQLite can add nullable columns with a plain ALTER, but relaxing
    # name's NOT NULL constraint (a place-linked activity legitimately has
    # no own name at all - see models.Activity) needs a full table rebuild,
    # hence batch mode for that one change. Bundled with place_id/rating/
    # review here too rather than a second rebuild right after.
    with op.batch_alter_table('activities', schema=None) as batch_op:
        batch_op.add_column(sa.Column('place_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('rating', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('review', sa.Text(), nullable=True))
        batch_op.alter_column('name', existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('activities', schema=None) as batch_op:
        batch_op.alter_column('name', existing_type=sa.String(), nullable=False)
        batch_op.drop_column('review')
        batch_op.drop_column('rating')
        batch_op.drop_column('place_id')

    op.drop_table('place_images')
    op.drop_table('places')
