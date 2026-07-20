"""Fiziksel depo semasi ve migration backfill kontrolleri."""

from decimal import Decimal
from pathlib import Path
from runpy import run_path

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.catalog import CartonType, Product
from app.models.inventory import Carton, WarehouseLocation, WarehouseRack


PHYSICAL_MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "20260720_0002_add_physical_rack_and_carton_placement.py"
)
PRODUCT_DIMENSION_MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "20260720_0003_add_product_physical_dimensions.py"
)


def test_physical_migration_revision_and_columns(db_session: Session) -> None:
    physical_migration = run_path(str(PHYSICAL_MIGRATION_PATH))
    product_migration = run_path(str(PRODUCT_DIMENSION_MIGRATION_PATH))
    database = inspect(db_session.get_bind())

    assert physical_migration["revision"] == "20260720_0002"
    assert physical_migration["down_revision"] == "20260714_0001"
    assert product_migration["revision"] == "20260720_0003"
    assert product_migration["down_revision"] == "20260720_0002"
    assert {
        "outer_length_cm",
        "outer_width_cm",
        "outer_height_cm",
    } <= {column["name"] for column in database.get_columns("carton_types")}
    assert {
        "position_x_cm",
        "position_y_cm",
        "position_z_cm",
        "rotation_degrees",
    } <= {column["name"] for column in database.get_columns("cartons")}
    assert "warehouse_racks" in database.get_table_names()
    assert {
        "unit_length_cm",
        "unit_width_cm",
        "unit_height_cm",
    } <= {column["name"] for column in database.get_columns("products")}
    assert "rack_id" in {
        column["name"] for column in database.get_columns("warehouse_locations")
    }


def test_migration_backfill_keeps_existing_physical_data_consistent(
    db_session: Session,
) -> None:
    invalid_carton_type_count = db_session.scalar(
        select(func.count(CartonType.id)).where(
            (CartonType.outer_length_cm < CartonType.inner_length_cm)
            | (CartonType.outer_width_cm < CartonType.inner_width_cm)
            | (CartonType.outer_height_cm < CartonType.inner_height_cm)
        )
    )
    location_without_rack_count = db_session.scalar(
        select(func.count(WarehouseLocation.id)).where(
            WarehouseLocation.rack_id.is_(None)
        )
    )
    incomplete_carton_placement_count = db_session.scalar(
        select(func.count(Carton.id)).where(
            (
                Carton.current_location_id.is_(None)
                & (
                    Carton.position_x_cm.is_not(None)
                    | Carton.position_y_cm.is_not(None)
                    | Carton.position_z_cm.is_not(None)
                    | Carton.rotation_degrees.is_not(None)
                )
            )
            | (
                Carton.current_location_id.is_not(None)
                & (
                    Carton.position_x_cm.is_(None)
                    | Carton.position_y_cm.is_(None)
                    | Carton.position_z_cm.is_(None)
                    | Carton.rotation_degrees.is_(None)
                )
            )
        )
    )
    incomplete_product_dimension_count = db_session.scalar(
        select(func.count(Product.id)).where(
            (
                Product.unit_length_cm.is_(None)
                | Product.unit_width_cm.is_(None)
                | Product.unit_height_cm.is_(None)
            ),
            (
                Product.unit_length_cm.is_not(None)
                | Product.unit_width_cm.is_not(None)
                | Product.unit_height_cm.is_not(None)
            ),
        )
    )

    assert invalid_carton_type_count == 0
    assert location_without_rack_count == 0
    assert incomplete_carton_placement_count == 0
    assert incomplete_product_dimension_count == 0


def test_database_rejects_rack_without_usable_width(db_session: Session) -> None:
    rack = WarehouseRack(
        aisle="INVALID-RACK-WIDTH",
        bay="B01",
        width_cm=Decimal("15.00"),
        depth_cm=Decimal("90.00"),
        level_clear_height_cm=Decimal("60.00"),
        level_count=1,
        slots_per_level=2,
        frame_thickness_cm=Decimal("5.00"),
        is_active=True,
    )

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(rack)
        db_session.flush()


def test_database_rejects_outer_dimension_smaller_than_inner(
    db_session: Session,
) -> None:
    carton_type = CartonType(
        code="INVALID-PHYSICAL-CARTON-TYPE",
        name="Invalid Physical Carton Type",
        inner_length_cm=Decimal("40.00"),
        inner_width_cm=Decimal("30.00"),
        inner_height_cm=Decimal("25.00"),
        outer_length_cm=Decimal("39.00"),
        outer_width_cm=Decimal("32.00"),
        outer_height_cm=Decimal("27.00"),
        max_weight_kg=Decimal("20.000"),
        is_active=True,
    )

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(carton_type)
        db_session.flush()
