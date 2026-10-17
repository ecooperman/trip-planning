"""add stay price worksheet and comparison criteria

Revision ID: c4b1a7d9e620
Revises: 500ff36719bd
Create Date: 2026-09-10 10:00:00.000000

Purely additive: new nullable columns on `stays`, one column on `trips`
(NOT NULL with a server default so existing rows fill in), and the two
new comparison tables. No data is moved or dropped on the way up.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4b1a7d9e620'
down_revision: Union[str, Sequence[str], None] = '500ff36719bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('trips', schema=None) as batch_op:
        batch_op.add_column(sa.Column('home_currency', sa.String(), nullable=False, server_default='USD'))

    with op.batch_alter_table('stays', schema=None) as batch_op:
        batch_op.add_column(sa.Column('listing_currency', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('nightly_price', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('total_price', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('extra_fees', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('fx_rate', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('bedrooms', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('bathrooms', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('sleeps', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('needs_review', sa.Boolean(), nullable=False, server_default='0'))

    op.create_table(
        'trip_stay_criteria',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('weight', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('must_have', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'stay_criterion_verdicts',
        sa.Column('stay_id', sa.Integer(), nullable=False),
        sa.Column('criterion_id', sa.Integer(), nullable=False),
        sa.Column('verdict', sa.String(), nullable=False, server_default='unknown'),
        sa.Column('note', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['stay_id'], ['stays.id'], ),
        sa.ForeignKeyConstraint(['criterion_id'], ['trip_stay_criteria.id'], ),
        sa.PrimaryKeyConstraint('stay_id', 'criterion_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('stay_criterion_verdicts')
    op.drop_table('trip_stay_criteria')

    with op.batch_alter_table('stays', schema=None) as batch_op:
        batch_op.drop_column('needs_review')
        batch_op.drop_column('sleeps')
        batch_op.drop_column('bathrooms')
        batch_op.drop_column('bedrooms')
        batch_op.drop_column('fx_rate')
        batch_op.drop_column('extra_fees')
        batch_op.drop_column('total_price')
        batch_op.drop_column('nightly_price')
        batch_op.drop_column('listing_currency')

    with op.batch_alter_table('trips', schema=None) as batch_op:
        batch_op.drop_column('home_currency')
