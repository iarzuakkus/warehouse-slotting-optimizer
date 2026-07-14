"""create_initial_warehouse_schema

Revision ID: 20260714_0001
Revises:
Create Date: 2026-07-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260714_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    """TimestampMixin ile aynı iki ortak kolonu üretir."""
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("unit_weight_kg", sa.Numeric(12, 3), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *timestamps(),
        sa.CheckConstraint("unit_weight_kg IS NULL OR unit_weight_kg > 0", name=op.f("ck_products_unit_weight_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("sku", name=op.f("uq_products_sku")),
    )
    op.create_table(
        "carton_types",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("inner_length_cm", sa.Numeric(10, 2), nullable=False),
        sa.Column("inner_width_cm", sa.Numeric(10, 2), nullable=False),
        sa.Column("inner_height_cm", sa.Numeric(10, 2), nullable=False),
        sa.Column("max_weight_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *timestamps(),
        sa.CheckConstraint("inner_length_cm > 0", name=op.f("ck_carton_types_inner_length_positive")),
        sa.CheckConstraint("inner_width_cm > 0", name=op.f("ck_carton_types_inner_width_positive")),
        sa.CheckConstraint("inner_height_cm > 0", name=op.f("ck_carton_types_inner_height_positive")),
        sa.CheckConstraint("max_weight_kg > 0", name=op.f("ck_carton_types_max_weight_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_carton_types")),
        sa.UniqueConstraint("code", name=op.f("uq_carton_types_code")),
    )
    op.create_table(
        "warehouse_locations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("aisle", sa.String(30), nullable=False),
        sa.Column("bay", sa.String(30), nullable=False),
        sa.Column("level", sa.String(30), nullable=False),
        sa.Column("slot", sa.String(30), nullable=False),
        sa.Column("max_weight_kg", sa.Numeric(12, 3), nullable=True),
        sa.Column("distance_from_dispatch_m", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *timestamps(),
        sa.CheckConstraint("max_weight_kg IS NULL OR max_weight_kg > 0", name=op.f("ck_warehouse_locations_max_weight_positive")),
        sa.CheckConstraint("distance_from_dispatch_m >= 0", name=op.f("ck_warehouse_locations_distance_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_warehouse_locations")),
        sa.UniqueConstraint("aisle", "bay", "level", "slot", name=op.f("uq_warehouse_locations_aisle_bay_level_slot")),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("order_number", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("ordered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("status IN ('pending', 'allocated', 'picking', 'completed', 'cancelled')", name=op.f("ck_orders_status_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("order_number", name=op.f("uq_orders_order_number")),
    )
    op.create_index("ix_orders_status_ordered_at", "orders", ["status", "ordered_at"])
    op.create_table(
        "optimization_runs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("algorithm_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("parameters", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("objective_value", sa.Numeric(18, 6), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(1000), nullable=True),
        *timestamps(),
        sa.CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'cancelled')", name=op.f("ck_optimization_runs_status_valid")),
        sa.CheckConstraint("completed_at IS NULL OR completed_at >= started_at", name=op.f("ck_optimization_runs_completion_after_start")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_optimization_runs")),
    )
    op.create_index("ix_optimization_runs_status_started_at", "optimization_runs", ["status", "started_at"])
    op.create_table(
        "product_packaging",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("carton_type_id", sa.BigInteger(), nullable=False),
        sa.Column("units_per_carton", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *timestamps(),
        sa.CheckConstraint("units_per_carton > 0", name=op.f("ck_product_packaging_units_per_carton_positive")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_product_packaging_product_id_products"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["carton_type_id"], ["carton_types.id"], name=op.f("fk_product_packaging_carton_type_id_carton_types"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_packaging")),
        sa.UniqueConstraint("product_id", "carton_type_id", name=op.f("uq_product_packaging_product_id_carton_type_id")),
    )
    op.create_index("ix_product_packaging_product_id", "product_packaging", ["product_id"])
    op.create_index("ix_product_packaging_carton_type_id", "product_packaging", ["carton_type_id"])
    op.create_table(
        "order_lines",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("ordered_qty", sa.Integer(), nullable=False),
        sa.Column("fulfilled_qty", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *timestamps(),
        sa.CheckConstraint("ordered_qty > 0", name=op.f("ck_order_lines_ordered_qty_positive")),
        sa.CheckConstraint("fulfilled_qty >= 0", name=op.f("ck_order_lines_fulfilled_qty_non_negative")),
        sa.CheckConstraint("fulfilled_qty <= ordered_qty", name=op.f("ck_order_lines_fulfilled_qty_within_ordered")),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_order_lines_order_id_orders"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_order_lines_product_id_products"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_lines")),
        sa.UniqueConstraint("order_id", "product_id", name=op.f("uq_order_lines_order_id_product_id")),
    )
    op.create_index("ix_order_lines_order_id", "order_lines", ["order_id"])
    op.create_index("ix_order_lines_product_id", "order_lines", ["product_id"])
    op.create_table(
        "cartons",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("carton_number", sa.String(80), nullable=False),
        sa.Column("product_packaging_id", sa.BigInteger(), nullable=False),
        sa.Column("current_location_id", sa.BigInteger(), nullable=True),
        sa.Column("capacity_qty", sa.Integer(), nullable=False),
        sa.Column("current_qty", sa.Integer(), nullable=False),
        sa.Column("reserved_qty", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(30), server_default=sa.text("'available'"), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("capacity_qty > 0", name=op.f("ck_cartons_capacity_positive")),
        sa.CheckConstraint("current_qty >= 0", name=op.f("ck_cartons_current_qty_non_negative")),
        sa.CheckConstraint("current_qty <= capacity_qty", name=op.f("ck_cartons_current_qty_within_capacity")),
        sa.CheckConstraint("reserved_qty >= 0", name=op.f("ck_cartons_reserved_qty_non_negative")),
        sa.CheckConstraint("reserved_qty <= current_qty", name=op.f("ck_cartons_reserved_qty_within_current")),
        sa.CheckConstraint("status IN ('available', 'reserved', 'depleted', 'quarantined')", name=op.f("ck_cartons_status_valid")),
        sa.ForeignKeyConstraint(["product_packaging_id"], ["product_packaging.id"], name=op.f("fk_cartons_product_packaging_id_product_packaging"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["current_location_id"], ["warehouse_locations.id"], name=op.f("fk_cartons_current_location_id_warehouse_locations"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cartons")),
        sa.UniqueConstraint("carton_number", name=op.f("uq_cartons_carton_number")),
    )
    op.create_index("ix_cartons_product_packaging_id", "cartons", ["product_packaging_id"])
    op.create_index("ix_cartons_current_location_id", "cartons", ["current_location_id"])
    op.create_index("ix_cartons_status_current_location_id", "cartons", ["status", "current_location_id"])
    op.create_table(
        "optimization_assignments",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("optimization_run_id", sa.BigInteger(), nullable=False),
        sa.Column("carton_id", sa.BigInteger(), nullable=False),
        sa.Column("from_location_id", sa.BigInteger(), nullable=True),
        sa.Column("to_location_id", sa.BigInteger(), nullable=False),
        sa.Column("assignment_score", sa.Numeric(18, 6), nullable=True),
        sa.CheckConstraint("from_location_id <> to_location_id", name=op.f("ck_optimization_assignments_locations_differ")),
        sa.ForeignKeyConstraint(["optimization_run_id"], ["optimization_runs.id"], name=op.f("fk_optimization_assignments_optimization_run_id_optimization_runs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["carton_id"], ["cartons.id"], name=op.f("fk_optimization_assignments_carton_id_cartons"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_location_id"], ["warehouse_locations.id"], name=op.f("fk_optimization_assignments_from_location_id_warehouse_locations"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["to_location_id"], ["warehouse_locations.id"], name=op.f("fk_optimization_assignments_to_location_id_warehouse_locations"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_optimization_assignments")),
        sa.UniqueConstraint("optimization_run_id", "carton_id", name=op.f("uq_optimization_assignments_optimization_run_id_carton_id")),
    )
    op.create_index("ix_optimization_assignments_optimization_run_id", "optimization_assignments", ["optimization_run_id"])
    op.create_index("ix_optimization_assignments_carton_id", "optimization_assignments", ["carton_id"])
    op.create_index("ix_optimization_assignments_to_location_id", "optimization_assignments", ["to_location_id"])
    op.create_table(
        "carton_allocations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("order_line_id", sa.BigInteger(), nullable=False),
        sa.Column("carton_id", sa.BigInteger(), nullable=False),
        sa.Column("allocated_qty", sa.Integer(), nullable=False),
        sa.Column("picked_qty", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(30), server_default=sa.text("'allocated'"), nullable=False),
        *timestamps(),
        sa.CheckConstraint("allocated_qty > 0", name=op.f("ck_carton_allocations_allocated_qty_positive")),
        sa.CheckConstraint("picked_qty >= 0", name=op.f("ck_carton_allocations_picked_qty_non_negative")),
        sa.CheckConstraint("picked_qty <= allocated_qty", name=op.f("ck_carton_allocations_picked_qty_within_allocated")),
        sa.CheckConstraint("status IN ('allocated', 'picking', 'picked', 'cancelled')", name=op.f("ck_carton_allocations_status_valid")),
        sa.ForeignKeyConstraint(["order_line_id"], ["order_lines.id"], name=op.f("fk_carton_allocations_order_line_id_order_lines"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["carton_id"], ["cartons.id"], name=op.f("fk_carton_allocations_carton_id_cartons"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_carton_allocations")),
        sa.UniqueConstraint("order_line_id", "carton_id", name=op.f("uq_carton_allocations_order_line_id_carton_id")),
    )
    op.create_index("ix_carton_allocations_order_line_id", "carton_allocations", ["order_line_id"])
    op.create_index("ix_carton_allocations_carton_id", "carton_allocations", ["carton_id"])
    op.create_index("ix_carton_allocations_status", "carton_allocations", ["status"])
    op.create_table(
        "carton_location_history",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("carton_id", sa.BigInteger(), nullable=False),
        sa.Column("from_location_id", sa.BigInteger(), nullable=True),
        sa.Column("to_location_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("moved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("from_location_id IS NOT NULL OR to_location_id IS NOT NULL", name=op.f("ck_carton_location_history_at_least_one_location")),
        sa.CheckConstraint("from_location_id IS NULL OR to_location_id IS NULL OR from_location_id <> to_location_id", name=op.f("ck_carton_location_history_locations_differ")),
        sa.ForeignKeyConstraint(["carton_id"], ["cartons.id"], name=op.f("fk_carton_location_history_carton_id_cartons"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_location_id"], ["warehouse_locations.id"], name=op.f("fk_carton_location_history_from_location_id_warehouse_locations"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["to_location_id"], ["warehouse_locations.id"], name=op.f("fk_carton_location_history_to_location_id_warehouse_locations"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_carton_location_history")),
    )
    op.create_index("ix_carton_location_history_carton_id_moved_at", "carton_location_history", ["carton_id", "moved_at"])
    op.create_table(
        "pick_operations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("allocation_id", sa.BigInteger(), nullable=False),
        sa.Column("location_id", sa.BigInteger(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("operator_reference", sa.String(100), nullable=True),
        sa.Column("picked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_pick_operations_quantity_positive")),
        sa.ForeignKeyConstraint(["allocation_id"], ["carton_allocations.id"], name=op.f("fk_pick_operations_allocation_id_carton_allocations"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["warehouse_locations.id"], name=op.f("fk_pick_operations_location_id_warehouse_locations"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pick_operations")),
    )
    op.create_index("ix_pick_operations_allocation_id_picked_at", "pick_operations", ["allocation_id", "picked_at"])
    op.create_index("ix_pick_operations_location_id", "pick_operations", ["location_id"])


def downgrade() -> None:
    op.drop_index("ix_pick_operations_location_id", table_name="pick_operations")
    op.drop_index("ix_pick_operations_allocation_id_picked_at", table_name="pick_operations")
    op.drop_table("pick_operations")
    op.drop_index("ix_carton_location_history_carton_id_moved_at", table_name="carton_location_history")
    op.drop_table("carton_location_history")
    op.drop_index("ix_carton_allocations_status", table_name="carton_allocations")
    op.drop_index("ix_carton_allocations_carton_id", table_name="carton_allocations")
    op.drop_index("ix_carton_allocations_order_line_id", table_name="carton_allocations")
    op.drop_table("carton_allocations")
    op.drop_index("ix_optimization_assignments_to_location_id", table_name="optimization_assignments")
    op.drop_index("ix_optimization_assignments_carton_id", table_name="optimization_assignments")
    op.drop_index("ix_optimization_assignments_optimization_run_id", table_name="optimization_assignments")
    op.drop_table("optimization_assignments")
    op.drop_index("ix_cartons_status_current_location_id", table_name="cartons")
    op.drop_index("ix_cartons_current_location_id", table_name="cartons")
    op.drop_index("ix_cartons_product_packaging_id", table_name="cartons")
    op.drop_table("cartons")
    op.drop_index("ix_order_lines_product_id", table_name="order_lines")
    op.drop_index("ix_order_lines_order_id", table_name="order_lines")
    op.drop_table("order_lines")
    op.drop_index("ix_product_packaging_carton_type_id", table_name="product_packaging")
    op.drop_index("ix_product_packaging_product_id", table_name="product_packaging")
    op.drop_table("product_packaging")
    op.drop_index("ix_optimization_runs_status_started_at", table_name="optimization_runs")
    op.drop_table("optimization_runs")
    op.drop_index("ix_orders_status_ordered_at", table_name="orders")
    op.drop_table("orders")
    op.drop_table("warehouse_locations")
    op.drop_table("carton_types")
    op.drop_table("products")
