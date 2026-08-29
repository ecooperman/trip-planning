"""add travel segments

Revision ID: a74533fdedf1
Revises: 67d7466b270d
Create Date: 2026-08-28 16:34:21.299176

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a74533fdedf1'
down_revision: Union[str, Sequence[str], None] = '67d7466b270d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'travel_segments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Enum('flight', 'train', 'rental_car', 'ferry', 'other', name='traveltype'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('confirmation_number', sa.String(), nullable=True),
        sa.Column('carrier', sa.String(), nullable=True),
        sa.Column('number', sa.String(), nullable=True),
        sa.Column('departure_location', sa.String(), nullable=True),
        sa.Column('arrival_location', sa.String(), nullable=True),
        sa.Column('departure_time', sa.DateTime(), nullable=True),
        sa.Column('arrival_time', sa.DateTime(), nullable=True),
        sa.Column('cost', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('booked', sa.Boolean(), nullable=False),
        sa.Column('archived', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('travel_segments')
