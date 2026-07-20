"""add product physical dimensions

Revision ID: 20260720_0003
Revises: 20260720_0002
Create Date: 2026-07-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260720_0003"
down_revision: str | None = "20260720_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DIMENSION_COLUMNS = (
    ("unit_length_cm", "unit_length_positive"),
    ("unit_width_cm", "unit_width_positive"),
    ("unit_height_cm", "unit_height_positive"),
)


def upgrade() -> None:
    for column_name, constraint_name in DIMENSION_COLUMNS:
        op.add_column(
            "products",
            sa.Column(column_name, sa.Numeric(10, 2), nullable=True),
        )
        op.create_check_constraint(
            op.f(f"ck_products_{constraint_name}"),
            "products",
            f"{column_name} IS NULL OR {column_name} > 0",
        )
    op.create_check_constraint(
        op.f("ck_products_unit_dimensions_complete"),
        "products",
        "(unit_length_cm IS NULL AND unit_width_cm IS NULL "
        "AND unit_height_cm IS NULL) OR "
        "(unit_length_cm IS NOT NULL AND unit_width_cm IS NOT NULL "
        "AND unit_height_cm IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_products_unit_dimensions_complete"),
        "products",
        type_="check",
    )
    for column_name, constraint_name in reversed(DIMENSION_COLUMNS):
        op.drop_constraint(
            op.f(f"ck_products_{constraint_name}"),
            "products",
            type_="check",
        )
        op.drop_column("products", column_name)
