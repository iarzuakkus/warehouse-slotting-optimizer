"""add simulation scenario fields

Revision ID: 20260721_0004
Revises: 20260720_0003
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260721_0004"
down_revision: str | None = "20260720_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _add_scenario_columns()
    _add_assignment_columns()
    _backfill_existing_assignments()
    _add_scenario_constraints()
    _add_assignment_constraints_and_indexes()


def _add_scenario_columns() -> None:
    op.add_column(
        "optimization_runs",
        sa.Column("name", sa.String(200), nullable=True),
    )
    op.add_column(
        "optimization_runs",
        sa.Column("seed", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "optimization_runs",
        sa.Column(
            "progress_percent",
            sa.Numeric(5, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "optimization_runs",
        sa.Column("source_snapshot", sa.JSON(), nullable=True),
    )
    op.add_column(
        "optimization_runs",
        sa.Column("result_metrics", sa.JSON(), nullable=True),
    )


def _add_assignment_columns() -> None:
    op.add_column(
        "optimization_assignments",
        sa.Column("sequence_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "optimization_assignments",
        sa.Column(
            "result_status",
            sa.String(30),
            server_default=sa.text("'placed'"),
            nullable=False,
        ),
    )
    for column_name in (
        "from_position_x_cm",
        "from_position_y_cm",
        "from_position_z_cm",
    ):
        op.add_column(
            "optimization_assignments",
            sa.Column(column_name, sa.Numeric(10, 2), nullable=True),
        )
    op.add_column(
        "optimization_assignments",
        sa.Column("from_rotation_degrees", sa.Integer(), nullable=True),
    )
    op.add_column(
        "optimization_assignments",
        sa.Column(
            "estimated_duration_seconds",
            sa.Numeric(10, 2),
            nullable=True,
        ),
    )
    op.add_column(
        "optimization_assignments",
        sa.Column("travel_distance_m", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "optimization_assignments",
        sa.Column(
            "movement_path",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
    )
    op.add_column(
        "optimization_assignments",
        sa.Column(
            "reasons",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
    )
    op.add_column(
        "optimization_assignments",
        sa.Column("unplaced_reason", sa.String(1000), nullable=True),
    )
    op.alter_column(
        "optimization_assignments",
        "to_location_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )


def _backfill_existing_assignments() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            WITH ordered_assignments AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY optimization_run_id
                        ORDER BY id
                    ) AS sequence_number
                FROM optimization_assignments
            )
            UPDATE optimization_assignments AS assignment
            SET sequence_number = ordered.sequence_number
            FROM ordered_assignments AS ordered
            WHERE ordered.id = assignment.id
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE optimization_assignments AS assignment
            SET from_position_x_cm = carton.position_x_cm,
                from_position_y_cm = carton.position_y_cm,
                from_position_z_cm = carton.position_z_cm,
                from_rotation_degrees = carton.rotation_degrees
            FROM cartons AS carton
            WHERE carton.id = assignment.carton_id
              AND carton.current_location_id = assignment.from_location_id
            """
        )
    )


def _add_scenario_constraints() -> None:
    op.create_check_constraint(
        op.f("ck_optimization_runs_progress_percent_range"),
        "optimization_runs",
        "progress_percent >= 0 AND progress_percent <= 100",
    )


def _add_assignment_constraints_and_indexes() -> None:
    checks = {
        "ck_optimization_assignments_from_rotation_valid": (
            "from_rotation_degrees IS NULL "
            "OR from_rotation_degrees IN (0, 90)"
        ),
        "ck_optimization_assignments_from_placement_complete": (
            "(from_position_x_cm IS NULL "
            "AND from_position_y_cm IS NULL "
            "AND from_position_z_cm IS NULL "
            "AND from_rotation_degrees IS NULL) "
            "OR (from_position_x_cm IS NOT NULL "
            "AND from_position_y_cm IS NOT NULL "
            "AND from_position_z_cm IS NOT NULL "
            "AND from_rotation_degrees IS NOT NULL)"
        ),
        "ck_optimization_assignments_sequence_number_positive": (
            "sequence_number IS NULL OR sequence_number > 0"
        ),
        "ck_optimization_assignments_estimated_duration_non_negative": (
            "estimated_duration_seconds IS NULL "
            "OR estimated_duration_seconds >= 0"
        ),
        "ck_optimization_assignments_travel_distance_non_negative": (
            "travel_distance_m IS NULL OR travel_distance_m >= 0"
        ),
        "ck_optimization_assignments_result_status_valid": (
            "result_status IN ('placed', 'unplaced')"
        ),
    }
    for constraint_name, condition in checks.items():
        op.create_check_constraint(
            op.f(constraint_name),
            "optimization_assignments",
            condition,
        )

    op.create_unique_constraint(
        op.f(
            "uq_optimization_assignments_optimization_run_id_sequence_number"
        ),
        "optimization_assignments",
        ["optimization_run_id", "sequence_number"],
    )
    op.create_index(
        "ix_optimization_assignments_run_sequence",
        "optimization_assignments",
        ["optimization_run_id", "sequence_number"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_optimization_assignments_run_sequence",
        table_name="optimization_assignments",
    )
    op.drop_constraint(
        op.f(
            "uq_optimization_assignments_optimization_run_id_sequence_number"
        ),
        "optimization_assignments",
        type_="unique",
    )

    assignment_checks = (
        "ck_optimization_assignments_result_status_valid",
        "ck_optimization_assignments_travel_distance_non_negative",
        "ck_optimization_assignments_estimated_duration_non_negative",
        "ck_optimization_assignments_sequence_number_positive",
        "ck_optimization_assignments_from_placement_complete",
        "ck_optimization_assignments_from_rotation_valid",
    )
    for constraint_name in assignment_checks:
        op.drop_constraint(
            op.f(constraint_name),
            "optimization_assignments",
            type_="check",
        )

    op.get_bind().execute(
        sa.text(
            "DELETE FROM optimization_assignments WHERE to_location_id IS NULL"
        )
    )
    op.alter_column(
        "optimization_assignments",
        "to_location_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    assignment_columns = (
        "unplaced_reason",
        "reasons",
        "movement_path",
        "travel_distance_m",
        "estimated_duration_seconds",
        "from_rotation_degrees",
        "from_position_z_cm",
        "from_position_y_cm",
        "from_position_x_cm",
        "result_status",
        "sequence_number",
    )
    for column_name in assignment_columns:
        op.drop_column("optimization_assignments", column_name)

    op.drop_constraint(
        op.f("ck_optimization_runs_progress_percent_range"),
        "optimization_runs",
        type_="check",
    )
    for column_name in (
        "result_metrics",
        "source_snapshot",
        "progress_percent",
        "seed",
        "name",
    ):
        op.drop_column("optimization_runs", column_name)
