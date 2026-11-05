"""add users and trip sharing

users, and trip_members (who can reach which trip, as owner / edit / view).
Trips, activities, places and categories each get an owner.

Everything that exists now is parked on a placeholder user
(legacy-owner@trips.invalid); the first person to sign in takes the
placeholder over (app/crud.py get_or_create_user), so it all becomes theirs
without moving a row. Each existing trip gets an owner row in trip_members.

Category names go from unique across the table to unique per owner.

Revision ID: c3d8e5a21f74
Revises: b7e2d4a91c03
Create Date: 2026-11-03 10:00:00.000000

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d8e5a21f74'
down_revision: Union[str, Sequence[str], None] = 'b7e2d4a91c03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_OWNER_EMAIL = "legacy-owner@trips.invalid"
OWNED_TABLES = ("trips", "activities", "places", "categories")

# SQLite reports the old unnamed UNIQUE(name) on categories only if told how
# it would have been named, which lets batch mode drop it.
CATEGORY_NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    conn = op.get_bind()
    conn.execute(
        sa.text("INSERT INTO users (email, created_at) VALUES (:email, :now)"),
        {"email": LEGACY_OWNER_EMAIL, "now": datetime.utcnow()},
    )
    legacy_id = conn.execute(sa.text("SELECT id FROM users WHERE email = :e"), {"e": LEGACY_OWNER_EMAIL}).scalar()

    op.create_table(
        "trip_members",
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("trip_id", "user_id"),
    )

    # owner_id starts nullable so the existing rows can be filled in.
    for table in OWNED_TABLES:
        naming = CATEGORY_NAMING if table == "categories" else None
        with op.batch_alter_table(table, naming_convention=naming) as batch_op:
            batch_op.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(f"fk_{table}_owner_id_users", "users", ["owner_id"], ["id"])
        conn.execute(sa.text(f"UPDATE {table} SET owner_id = :owner"), {"owner": legacy_id})

    conn.execute(sa.text("INSERT INTO trip_members (trip_id, user_id, role) SELECT id, owner_id, 'owner' FROM trips"))

    for table in OWNED_TABLES:
        naming = CATEGORY_NAMING if table == "categories" else None
        with op.batch_alter_table(table, naming_convention=naming) as batch_op:
            batch_op.alter_column("owner_id", existing_type=sa.Integer(), nullable=False)
            if table == "categories":
                batch_op.drop_constraint("uq_categories_name", type_="unique")
                batch_op.create_unique_constraint("uq_categories_owner_id_name", ["owner_id", "name"])


def downgrade() -> None:
    """Downgrade schema.

    Sharing is lost (only each trip's owner row matters). Fails if two people
    have a category with the same name (the old schema had one table-wide
    namespace)."""
    op.drop_table("trip_members")
    for table in reversed(OWNED_TABLES):
        naming = CATEGORY_NAMING if table == "categories" else None
        with op.batch_alter_table(table, naming_convention=naming) as batch_op:
            if table == "categories":
                batch_op.drop_constraint("uq_categories_owner_id_name", type_="unique")
            batch_op.drop_constraint(f"fk_{table}_owner_id_users", type_="foreignkey")
            batch_op.drop_column("owner_id")
            if table == "categories":
                batch_op.create_unique_constraint("uq_categories_name", ["name"])
    op.drop_table("users")
