"""generalize activity distance cache to locations

Revision ID: 67d7466b270d
Revises: a554e3cc5220
Create Date: 2026-08-28 16:13:47.885397

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67d7466b270d'
down_revision: Union[str, Sequence[str], None] = 'a554e3cc5220'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Replaces activity_distances (activity-only, plain FK columns) with
    location_distances (kind+id columns, so an endpoint can be an activity
    or a stay - see models.LocationDistance). This is a pure cache table -
    every row is freely recomputable from a live Google Distance Matrix
    call - so upgrading drops and recreates it rather than migrating rows;
    there's nothing worth preserving, and it sidesteps SQLite's batch-mode
    ALTER entirely for a rename this size.
    """
    op.drop_table('activity_distances')
    op.create_table(
        'location_distances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('origin_kind', sa.String(), nullable=False),
        sa.Column('origin_id', sa.Integer(), nullable=False),
        sa.Column('destination_kind', sa.String(), nullable=False),
        sa.Column('destination_id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column('distance_meters', sa.Integer(), nullable=False),
        sa.Column('distance_text', sa.String(), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('duration_text', sa.String(), nullable=False),
        sa.Column('computed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'origin_kind', 'origin_id', 'destination_kind', 'destination_id', 'mode',
            name='uq_location_distance_pair_mode',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('location_distances')
    op.create_table(
        'activity_distances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('origin_activity_id', sa.Integer(), nullable=False),
        sa.Column('destination_activity_id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column('distance_meters', sa.Integer(), nullable=False),
        sa.Column('distance_text', sa.String(), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('duration_text', sa.String(), nullable=False),
        sa.Column('computed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['destination_activity_id'], ['activities.id'], ),
        sa.ForeignKeyConstraint(['origin_activity_id'], ['activities.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('origin_activity_id', 'destination_activity_id', 'mode', name='uq_activity_distance_pair_mode'),
    )
