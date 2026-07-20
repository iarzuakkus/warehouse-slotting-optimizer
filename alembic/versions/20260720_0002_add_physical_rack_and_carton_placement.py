"""add physical rack and carton placement

Revision ID: 20260720_0002
Revises: 20260714_0001
Create Date: 2026-07-20
"""

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from alembic import op
import sqlalchemy as sa

from app.algorithms.carton_placement import (
    CartonDimensions,
    ContainerDimensions,
    PlacedCarton,
    find_placement,
    has_weight_capacity,
)


revision: str = "20260720_0002"
down_revision: str | None = "20260714_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SLOT_USABLE_WIDTH_CM = Decimal("100.00")
USABLE_DEPTH_CM = Decimal("80.00")
LEVEL_CLEAR_HEIGHT_CM = Decimal("60.00")
FRAME_THICKNESS_CM = Decimal("5.00")
OUTER_DIMENSION_PADDING_CM = Decimal("2.00")
BATCH_SIZE = 1_000


def timestamps() -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    _add_carton_type_outer_dimensions()
    _create_warehouse_racks()
    _add_placement_columns()
    _backfill_physical_structure()
    _enforce_physical_constraints()


def _add_carton_type_outer_dimensions() -> None:
    op.add_column(
        "carton_types",
        sa.Column("outer_length_cm", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "carton_types",
        sa.Column("outer_width_cm", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "carton_types",
        sa.Column("outer_height_cm", sa.Numeric(10, 2), nullable=True),
    )


def _create_warehouse_racks() -> None:
    op.create_table(
        "warehouse_racks",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("aisle", sa.String(30), nullable=False),
        sa.Column("bay", sa.String(30), nullable=False),
        sa.Column("width_cm", sa.Numeric(10, 2), nullable=False),
        sa.Column("depth_cm", sa.Numeric(10, 2), nullable=False),
        sa.Column("level_clear_height_cm", sa.Numeric(10, 2), nullable=False),
        sa.Column("level_count", sa.Integer(), nullable=False),
        sa.Column("slots_per_level", sa.Integer(), nullable=False),
        sa.Column("frame_thickness_cm", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        *timestamps(),
        sa.CheckConstraint(
            "width_cm > 0",
            name=op.f("ck_warehouse_racks_width_positive"),
        ),
        sa.CheckConstraint(
            "depth_cm > 0",
            name=op.f("ck_warehouse_racks_depth_positive"),
        ),
        sa.CheckConstraint(
            "level_clear_height_cm > 0",
            name=op.f("ck_warehouse_racks_level_clear_height_positive"),
        ),
        sa.CheckConstraint(
            "level_count > 0",
            name=op.f("ck_warehouse_racks_level_count_positive"),
        ),
        sa.CheckConstraint(
            "slots_per_level > 0",
            name=op.f("ck_warehouse_racks_slots_per_level_positive"),
        ),
        sa.CheckConstraint(
            "frame_thickness_cm > 0",
            name=op.f("ck_warehouse_racks_frame_thickness_positive"),
        ),
        sa.CheckConstraint(
            "width_cm > frame_thickness_cm * (slots_per_level + 1)",
            name=op.f("ck_warehouse_racks_width_has_usable_space"),
        ),
        sa.CheckConstraint(
            "depth_cm > frame_thickness_cm * 2",
            name=op.f("ck_warehouse_racks_depth_has_usable_space"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_warehouse_racks")),
        sa.UniqueConstraint(
            "aisle",
            "bay",
            name=op.f("uq_warehouse_racks_aisle_bay"),
        ),
    )

    op.add_column(
        "warehouse_locations",
        sa.Column("rack_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        op.f("ix_warehouse_locations_rack_id"),
        "warehouse_locations",
        ["rack_id"],
    )
    op.create_foreign_key(
        op.f("fk_warehouse_locations_rack_id_warehouse_racks"),
        "warehouse_locations",
        "warehouse_racks",
        ["rack_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def _add_placement_columns() -> None:
    for column_name in ("position_x_cm", "position_y_cm", "position_z_cm"):
        op.add_column(
            "cartons",
            sa.Column(column_name, sa.Numeric(10, 2), nullable=True),
        )
    op.add_column(
        "cartons",
        sa.Column("rotation_degrees", sa.Integer(), nullable=True),
    )

    for column_name in (
        "proposed_position_x_cm",
        "proposed_position_y_cm",
        "proposed_position_z_cm",
    ):
        op.add_column(
            "optimization_assignments",
            sa.Column(column_name, sa.Numeric(10, 2), nullable=True),
        )
    op.add_column(
        "optimization_assignments",
        sa.Column("proposed_rotation_degrees", sa.Integer(), nullable=True),
    )


def _backfill_physical_structure() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE carton_types
            SET outer_length_cm = inner_length_cm + :padding,
                outer_width_cm = inner_width_cm + :padding,
                outer_height_cm = inner_height_cm + :padding
            """
        ),
        {"padding": OUTER_DIMENSION_PADDING_CM},
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO warehouse_racks (
                aisle,
                bay,
                width_cm,
                depth_cm,
                level_clear_height_cm,
                level_count,
                slots_per_level,
                frame_thickness_cm,
                is_active
            )
            SELECT
                aisle,
                bay,
                COUNT(DISTINCT slot) * :slot_width
                    + (COUNT(DISTINCT slot) + 1) * :frame_thickness,
                :usable_depth + 2 * :frame_thickness,
                :level_height,
                COUNT(DISTINCT level),
                COUNT(DISTINCT slot),
                :frame_thickness,
                BOOL_OR(is_active)
            FROM warehouse_locations
            GROUP BY aisle, bay
            ORDER BY aisle, bay
            """
        ),
        {
            "slot_width": SLOT_USABLE_WIDTH_CM,
            "usable_depth": USABLE_DEPTH_CM,
            "level_height": LEVEL_CLEAR_HEIGHT_CM,
            "frame_thickness": FRAME_THICKNESS_CM,
        },
    )
    connection.execute(
        sa.text(
            """
            UPDATE warehouse_locations AS location
            SET rack_id = rack.id
            FROM warehouse_racks AS rack
            WHERE rack.aisle = location.aisle
              AND rack.bay = location.bay
            """
        )
    )
    _backfill_carton_placements(connection)


def _backfill_carton_placements(connection: sa.Connection) -> None:
    location_rows = list(
        connection.execute(
            sa.text(
                """
                SELECT
                    location.id,
                    location.max_weight_kg,
                    (rack.width_cm
                        - rack.frame_thickness_cm * (rack.slots_per_level + 1))
                        / rack.slots_per_level AS usable_width_cm,
                    rack.depth_cm - rack.frame_thickness_cm * 2
                        AS usable_depth_cm,
                    rack.level_clear_height_cm AS usable_height_cm
                FROM warehouse_locations AS location
                JOIN warehouse_racks AS rack ON rack.id = location.rack_id
                WHERE location.is_active = true
                  AND rack.is_active = true
                ORDER BY location.aisle, location.bay, location.level, location.slot
                """
            )
        ).mappings()
    )
    if not location_rows:
        connection.execute(
            sa.text(
                """
                UPDATE cartons
                SET current_location_id = NULL,
                    position_x_cm = NULL,
                    position_y_cm = NULL,
                    position_z_cm = NULL,
                    rotation_degrees = NULL
                """
            )
        )
        return

    location_by_id = {int(row["id"]): row for row in location_rows}
    ordered_location_ids = list(location_by_id)
    placed_by_location: dict[int, list[PlacedCarton]] = {
        location_id: [] for location_id in ordered_location_ids
    }
    used_weight_by_location = {
        location_id: Decimal("0") for location_id in ordered_location_ids
    }

    carton_rows = connection.execute(
        sa.text(
            """
            SELECT
                carton.id,
                carton.carton_number,
                carton.current_location_id,
                carton.current_qty,
                product.unit_weight_kg,
                carton_type.outer_length_cm,
                carton_type.outer_width_cm,
                carton_type.outer_height_cm
            FROM cartons AS carton
            JOIN product_packaging AS packaging
                ON packaging.id = carton.product_packaging_id
            JOIN products AS product ON product.id = packaging.product_id
            JOIN carton_types AS carton_type
                ON carton_type.id = packaging.carton_type_id
            ORDER BY carton.carton_number, carton.id
            """
        )
    ).mappings()

    updates: list[dict[str, Any]] = []
    for carton_index, carton in enumerate(carton_rows):
        preferred_location_id = carton["current_location_id"]
        round_robin_start = carton_index % len(ordered_location_ids)
        rotated_location_ids = (
            ordered_location_ids[round_robin_start:]
            + ordered_location_ids[:round_robin_start]
        )
        candidate_location_ids = rotated_location_ids
        if preferred_location_id in location_by_id:
            candidate_location_ids = [
                int(preferred_location_id),
                *(
                    location_id
                    for location_id in rotated_location_ids
                    if location_id != preferred_location_id
                ),
            ]

        unit_weight = carton["unit_weight_kg"]
        incoming_weight = (
            Decimal(carton["current_qty"]) * unit_weight
            if unit_weight is not None
            else None
        )
        dimensions = CartonDimensions(
            length_cm=carton["outer_length_cm"],
            width_cm=carton["outer_width_cm"],
            height_cm=carton["outer_height_cm"],
        )
        placement_update: dict[str, Any] | None = None
        for location_id in candidate_location_ids:
            location = location_by_id[location_id]
            if not has_weight_capacity(
                used_weight_by_location[location_id],
                incoming_weight,
                location["max_weight_kg"],
            ):
                continue
            placement = find_placement(
                ContainerDimensions(
                    width_cm=location["usable_width_cm"],
                    depth_cm=location["usable_depth_cm"],
                    height_cm=location["usable_height_cm"],
                ),
                dimensions,
                placed_by_location[location_id],
            )
            if placement is None:
                continue

            placed_by_location[location_id].append(
                placement.to_placed_carton(carton_id=int(carton["id"]))
            )
            used_weight_by_location[location_id] += incoming_weight
            placement_update = {
                "carton_id": carton["id"],
                "location_id": location_id,
                "position_x_cm": placement.position_x_cm,
                "position_y_cm": placement.position_y_cm,
                "position_z_cm": placement.position_z_cm,
                "rotation_degrees": placement.rotation_degrees,
            }
            break

        updates.append(
            placement_update
            or {
                "carton_id": carton["id"],
                "location_id": None,
                "position_x_cm": None,
                "position_y_cm": None,
                "position_z_cm": None,
                "rotation_degrees": None,
            }
        )
        if len(updates) >= BATCH_SIZE:
            _write_carton_placements(connection, updates)
            updates.clear()

    if updates:
        _write_carton_placements(connection, updates)


def _write_carton_placements(
    connection: sa.Connection,
    updates: list[dict[str, Any]],
) -> None:
    connection.execute(
        sa.text(
            """
            UPDATE cartons
            SET current_location_id = :location_id,
                position_x_cm = :position_x_cm,
                position_y_cm = :position_y_cm,
                position_z_cm = :position_z_cm,
                rotation_degrees = :rotation_degrees
            WHERE id = :carton_id
            """
        ),
        updates,
    )


def _enforce_physical_constraints() -> None:
    op.alter_column("carton_types", "outer_length_cm", nullable=False)
    op.alter_column("carton_types", "outer_width_cm", nullable=False)
    op.alter_column("carton_types", "outer_height_cm", nullable=False)
    op.alter_column("warehouse_locations", "rack_id", nullable=False)

    carton_type_checks = {
        "ck_carton_types_outer_length_positive": "outer_length_cm > 0",
        "ck_carton_types_outer_width_positive": "outer_width_cm > 0",
        "ck_carton_types_outer_height_positive": "outer_height_cm > 0",
        "ck_carton_types_outer_length_not_smaller_than_inner": (
            "outer_length_cm >= inner_length_cm"
        ),
        "ck_carton_types_outer_width_not_smaller_than_inner": (
            "outer_width_cm >= inner_width_cm"
        ),
        "ck_carton_types_outer_height_not_smaller_than_inner": (
            "outer_height_cm >= inner_height_cm"
        ),
    }
    for constraint_name, condition in carton_type_checks.items():
        op.create_check_constraint(
            op.f(constraint_name),
            "carton_types",
            condition,
        )

    carton_checks = {
        "ck_cartons_position_x_non_negative": (
            "position_x_cm IS NULL OR position_x_cm >= 0"
        ),
        "ck_cartons_position_y_non_negative": (
            "position_y_cm IS NULL OR position_y_cm >= 0"
        ),
        "ck_cartons_position_z_non_negative": (
            "position_z_cm IS NULL OR position_z_cm >= 0"
        ),
        "ck_cartons_rotation_valid": (
            "rotation_degrees IS NULL OR rotation_degrees IN (0, 90)"
        ),
        "ck_cartons_placement_complete_for_location": (
            "(current_location_id IS NULL "
            "AND position_x_cm IS NULL "
            "AND position_y_cm IS NULL "
            "AND position_z_cm IS NULL "
            "AND rotation_degrees IS NULL) "
            "OR (current_location_id IS NOT NULL "
            "AND position_x_cm IS NOT NULL "
            "AND position_y_cm IS NOT NULL "
            "AND position_z_cm IS NOT NULL "
            "AND rotation_degrees IS NOT NULL)"
        ),
    }
    for constraint_name, condition in carton_checks.items():
        op.create_check_constraint(op.f(constraint_name), "cartons", condition)

    assignment_checks = {
        "ck_optimization_assignments_proposed_position_x_non_negative": (
            "proposed_position_x_cm IS NULL OR proposed_position_x_cm >= 0"
        ),
        "ck_optimization_assignments_proposed_position_y_non_negative": (
            "proposed_position_y_cm IS NULL OR proposed_position_y_cm >= 0"
        ),
        "ck_optimization_assignments_proposed_position_z_non_negative": (
            "proposed_position_z_cm IS NULL OR proposed_position_z_cm >= 0"
        ),
        "ck_optimization_assignments_proposed_rotation_valid": (
            "proposed_rotation_degrees IS NULL "
            "OR proposed_rotation_degrees IN (0, 90)"
        ),
        "ck_optimization_assignments_proposed_placement_complete": (
            "(proposed_position_x_cm IS NULL "
            "AND proposed_position_y_cm IS NULL "
            "AND proposed_position_z_cm IS NULL "
            "AND proposed_rotation_degrees IS NULL) "
            "OR (proposed_position_x_cm IS NOT NULL "
            "AND proposed_position_y_cm IS NOT NULL "
            "AND proposed_position_z_cm IS NOT NULL "
            "AND proposed_rotation_degrees IS NOT NULL)"
        ),
    }
    for constraint_name, condition in assignment_checks.items():
        op.create_check_constraint(
            op.f(constraint_name),
            "optimization_assignments",
            condition,
        )


def downgrade() -> None:
    assignment_constraints = (
        "ck_optimization_assignments_proposed_placement_complete",
        "ck_optimization_assignments_proposed_rotation_valid",
        "ck_optimization_assignments_proposed_position_z_non_negative",
        "ck_optimization_assignments_proposed_position_y_non_negative",
        "ck_optimization_assignments_proposed_position_x_non_negative",
    )
    for constraint_name in assignment_constraints:
        op.drop_constraint(
            op.f(constraint_name),
            "optimization_assignments",
            type_="check",
        )
    op.drop_column("optimization_assignments", "proposed_rotation_degrees")
    op.drop_column("optimization_assignments", "proposed_position_z_cm")
    op.drop_column("optimization_assignments", "proposed_position_y_cm")
    op.drop_column("optimization_assignments", "proposed_position_x_cm")

    carton_constraints = (
        "ck_cartons_placement_complete_for_location",
        "ck_cartons_rotation_valid",
        "ck_cartons_position_z_non_negative",
        "ck_cartons_position_y_non_negative",
        "ck_cartons_position_x_non_negative",
    )
    for constraint_name in carton_constraints:
        op.drop_constraint(op.f(constraint_name), "cartons", type_="check")
    op.drop_column("cartons", "rotation_degrees")
    op.drop_column("cartons", "position_z_cm")
    op.drop_column("cartons", "position_y_cm")
    op.drop_column("cartons", "position_x_cm")

    op.drop_constraint(
        op.f("fk_warehouse_locations_rack_id_warehouse_racks"),
        "warehouse_locations",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_warehouse_locations_rack_id"),
        table_name="warehouse_locations",
    )
    op.drop_column("warehouse_locations", "rack_id")
    op.drop_table("warehouse_racks")

    carton_type_constraints = (
        "ck_carton_types_outer_height_not_smaller_than_inner",
        "ck_carton_types_outer_width_not_smaller_than_inner",
        "ck_carton_types_outer_length_not_smaller_than_inner",
        "ck_carton_types_outer_height_positive",
        "ck_carton_types_outer_width_positive",
        "ck_carton_types_outer_length_positive",
    )
    for constraint_name in carton_type_constraints:
        op.drop_constraint(op.f(constraint_name), "carton_types", type_="check")
    op.drop_column("carton_types", "outer_height_cm")
    op.drop_column("carton_types", "outer_width_cm")
    op.drop_column("carton_types", "outer_length_cm")
