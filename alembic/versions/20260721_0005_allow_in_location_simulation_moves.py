"""allow in-location simulation moves

Revision ID: 20260721_0005
Revises: 20260721_0004
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260721_0005"
down_revision: str | None = "20260721_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_optimization_assignments_locations_differ"),
        "optimization_assignments",
        type_="check",
    )
    op.create_check_constraint(
        op.f(
            "ck_optimization_assignments_locations_or_placement_differ"
        ),
        "optimization_assignments",
        "from_location_id IS NULL "
        "OR to_location_id IS NULL "
        "OR from_location_id <> to_location_id "
        "OR (from_position_x_cm IS NOT NULL "
        "AND from_position_y_cm IS NOT NULL "
        "AND from_position_z_cm IS NOT NULL "
        "AND from_rotation_degrees IS NOT NULL "
        "AND proposed_position_x_cm IS NOT NULL "
        "AND proposed_position_y_cm IS NOT NULL "
        "AND proposed_position_z_cm IS NOT NULL "
        "AND proposed_rotation_degrees IS NOT NULL "
        "AND (from_position_x_cm <> proposed_position_x_cm "
        "OR from_position_y_cm <> proposed_position_y_cm "
        "OR from_position_z_cm <> proposed_position_z_cm "
        "OR from_rotation_degrees <> proposed_rotation_degrees))",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f(
            "ck_optimization_assignments_locations_or_placement_differ"
        ),
        "optimization_assignments",
        type_="check",
    )
    op.get_bind().exec_driver_sql(
        "DELETE FROM optimization_assignments "
        "WHERE from_location_id = to_location_id"
    )
    op.create_check_constraint(
        op.f("ck_optimization_assignments_locations_differ"),
        "optimization_assignments",
        "from_location_id <> to_location_id",
    )
