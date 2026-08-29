"""add dog care bookings

Revision ID: d0c2c5684be4
Revises: a74533fdedf1
Create Date: 2026-08-29 08:48:13.163346

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0c2c5684be4'
down_revision: Union[str, Sequence[str], None] = 'a74533fdedf1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'dog_care_bookings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('company_name', sa.String(), nullable=False),
        sa.Column('walker_name', sa.String(), nullable=True),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('cost', sa.Integer(), nullable=True),
        sa.Column('start_date', sa.DateTime(), nullable=False),
        sa.Column('end_date', sa.DateTime(), nullable=False),
        sa.Column('booked', sa.Boolean(), nullable=False),
        sa.Column('archived', sa.Boolean(), nullable=False),
        sa.Column('invoice_filename', sa.String(), nullable=True),
        sa.Column('invoice_content_type', sa.String(), nullable=True),
        sa.Column('invoice_data', sa.LargeBinary(), nullable=True),
        sa.Column('instructions_filename', sa.String(), nullable=True),
        sa.Column('instructions_content_type', sa.String(), nullable=True),
        sa.Column('instructions_data', sa.LargeBinary(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('dog_care_bookings')
