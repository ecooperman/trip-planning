"""give activities.place_id its foreign key to places

The column was added without the constraint (a6808b8e52b5 added it inside a batch that rebuilt the
table, and the key never made it), while the model has always declared it. Rows are untouched: an
activity's place_id is null or already points at a real place (the app never wrote anything else).
`alembic check` is clean again afterwards.

Revision ID: b9c4e7a1d352
Revises: e3ae3d39f355
Create Date: 2026-11-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b9c4e7a1d352'
down_revision: Union[str, Sequence[str], None] = 'e3ae3d39f355'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Anything pointing at a place that no longer exists would break the rebuilt table's constraint;
    # clear such links first (there should be none).
    op.execute("UPDATE activities SET place_id = NULL WHERE place_id IS NOT NULL AND place_id NOT IN (SELECT id FROM places)")
    with op.batch_alter_table("activities") as batch_op:
        batch_op.create_foreign_key("fk_activities_place_id_places", "places", ["place_id"], ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("activities") as batch_op:
        batch_op.drop_constraint("fk_activities_place_id_places", type_="foreignkey")
