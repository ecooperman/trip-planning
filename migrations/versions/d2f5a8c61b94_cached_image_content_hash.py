"""cached images: content hash, so the same picture is stored once

Revision ID: d2f5a8c61b94
Revises: b9c4e7a1d352
Create Date: 2026-11-14 20:00:00.000000

"""
import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2f5a8c61b94'
down_revision: Union[str, Sequence[str], None] = 'b9c4e7a1d352'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('cached_images') as batch:
        batch.add_column(sa.Column('content_hash', sa.String(), nullable=True))
        batch.create_index('ix_cached_images_content_hash', ['content_hash'])

    # Fill it in for the pictures already kept. Copies of the same picture that were stored more than
    # once are left as they are (each is still pointed at by something); only new downloads are deduped.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, data FROM cached_images")).fetchall()
    for image_id, data in rows:
        bind.execute(
            sa.text("UPDATE cached_images SET content_hash = :h WHERE id = :i"),
            {"h": hashlib.sha256(bytes(data)).hexdigest(), "i": image_id},
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('cached_images') as batch:
        batch.drop_index('ix_cached_images_content_hash')
        batch.drop_column('content_hash')
