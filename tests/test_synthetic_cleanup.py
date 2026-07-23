"""Sentetik veri temizleme siniri ve guvenlik testleri."""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_generation.cleanup import (
    SyntheticCleanupSafetyError,
    delete_synthetic_data,
)
from app.models.catalog import CartonType, Product, ProductPackaging
from app.models.inventory import Carton, WarehouseLocation
from app.models.optimization import OptimizationAssignment, OptimizationRun
from tests.factories import create_warehouse_rack


def test_cleanup_deletes_only_synthetic_products(db_session: Session) -> None:
    synthetic = Product(
        sku="SYN-CLEANUP-PRODUCT",
        name="Synthetic Cleanup Product",
        unit_weight_kg=Decimal("1.000"),
        unit_length_cm=Decimal("10.00"),
        unit_width_cm=Decimal("10.00"),
        unit_height_cm=Decimal("10.00"),
        is_active=True,
    )
    manual = Product(
        sku="MANUAL-CLEANUP-PRODUCT",
        name="Manual Cleanup Product",
        unit_weight_kg=Decimal("1.000"),
        is_active=True,
    )
    db_session.add_all([synthetic, manual])
    db_session.flush()

    result = delete_synthetic_data(db_session)
    db_session.flush()

    assert result.product_count >= 1
    assert db_session.scalar(
        select(Product).where(Product.sku == "SYN-CLEANUP-PRODUCT")
    ) is None
    assert db_session.scalar(
        select(Product).where(Product.sku == "MANUAL-CLEANUP-PRODUCT")
    ) is manual


def test_cleanup_refuses_non_synthetic_carton_in_synthetic_location(
    db_session: Session,
) -> None:
    product = Product(
        sku="MANUAL-SAFETY-PRODUCT",
        name="Manual Safety Product",
        unit_weight_kg=Decimal("1.000"),
        is_active=True,
    )
    carton_type = CartonType(
        code="MANUAL-SAFETY-CT",
        name="Manual Safety Carton Type",
        inner_length_cm=Decimal("40.00"),
        inner_width_cm=Decimal("30.00"),
        inner_height_cm=Decimal("25.00"),
        outer_length_cm=Decimal("42.00"),
        outer_width_cm=Decimal("32.00"),
        outer_height_cm=Decimal("27.00"),
        max_weight_kg=Decimal("20.000"),
        is_active=True,
    )
    db_session.add_all([product, carton_type])
    db_session.flush()
    packaging = ProductPackaging(
        product_id=product.id,
        carton_type_id=carton_type.id,
        units_per_carton=10,
        is_default=True,
    )
    rack = create_warehouse_rack(
        db_session,
        aisle="SYN-A999",
        bay="B001",
        level_count=1,
        slots_per_level=1,
    )
    db_session.add(packaging)
    db_session.flush()
    location = WarehouseLocation(
        rack_id=rack.id,
        aisle=rack.aisle,
        bay=rack.bay,
        level="L01",
        slot="S01",
        max_weight_kg=Decimal("100.000"),
        distance_from_dispatch_m=Decimal("10.00"),
        is_active=True,
    )
    db_session.add(location)
    db_session.flush()
    db_session.add(
        Carton(
            carton_number="MANUAL-SAFETY-CARTON",
            product_packaging_id=packaging.id,
            current_location_id=location.id,
            position_x_cm=Decimal("0.00"),
            position_y_cm=Decimal("0.00"),
            position_z_cm=Decimal("0.00"),
            rotation_degrees=0,
            capacity_qty=10,
            current_qty=10,
            reserved_qty=0,
            status="available",
        )
    )
    db_session.flush()

    with pytest.raises(SyntheticCleanupSafetyError, match="referenced"):
        delete_synthetic_data(db_session)


def test_cleanup_deletes_scenario_referencing_synthetic_target_location(
    db_session: Session,
) -> None:
    product = Product(
        sku="MANUAL-CLEANUP-SCENARIO-PRODUCT",
        name="Manual Cleanup Scenario Product",
        unit_weight_kg=Decimal("1.000"),
        is_active=True,
    )
    carton_type = CartonType(
        code="MANUAL-CLEANUP-SCENARIO-CT",
        name="Manual Cleanup Scenario Carton Type",
        inner_length_cm=Decimal("40.00"),
        inner_width_cm=Decimal("30.00"),
        inner_height_cm=Decimal("25.00"),
        outer_length_cm=Decimal("42.00"),
        outer_width_cm=Decimal("32.00"),
        outer_height_cm=Decimal("27.00"),
        max_weight_kg=Decimal("20.000"),
        is_active=True,
    )
    db_session.add_all([product, carton_type])
    db_session.flush()
    packaging = ProductPackaging(
        product_id=product.id,
        carton_type_id=carton_type.id,
        units_per_carton=10,
        is_default=True,
    )
    rack = create_warehouse_rack(
        db_session,
        aisle="SYN-A998",
        bay="B001",
        level_count=1,
        slots_per_level=1,
    )
    db_session.add(packaging)
    db_session.flush()
    target_location = WarehouseLocation(
        rack_id=rack.id,
        aisle=rack.aisle,
        bay=rack.bay,
        level="L01",
        slot="S01",
        max_weight_kg=Decimal("100.000"),
        distance_from_dispatch_m=Decimal("10.00"),
        is_active=True,
    )
    carton = Carton(
        carton_number="MANUAL-CLEANUP-SCENARIO-CARTON",
        product_packaging_id=packaging.id,
        current_location_id=None,
        capacity_qty=10,
        current_qty=10,
        reserved_qty=0,
        status="available",
    )
    scenario = OptimizationRun(
        name="Synthetic Target Cleanup Scenario",
        seed=42,
        algorithm_name="deterministic_slotting_v1",
        status="completed",
    )
    db_session.add_all([target_location, carton, scenario])
    db_session.flush()
    assignment = OptimizationAssignment(
        optimization_run_id=scenario.id,
        carton_id=carton.id,
        sequence_number=1,
        result_status="placed",
        from_location_id=None,
        to_location_id=target_location.id,
        proposed_position_x_cm=Decimal("0.00"),
        proposed_position_y_cm=Decimal("0.00"),
        proposed_position_z_cm=Decimal("0.00"),
        proposed_rotation_degrees=0,
    )
    db_session.add(assignment)
    db_session.flush()
    scenario_id = scenario.id
    assignment_id = assignment.id
    carton_id = carton.id

    result = delete_synthetic_data(db_session)
    db_session.flush()

    assert result.optimization_run_count >= 1
    assert db_session.scalar(
        select(OptimizationRun.id).where(OptimizationRun.id == scenario_id)
    ) is None
    assert db_session.scalar(
        select(OptimizationAssignment.id).where(
            OptimizationAssignment.id == assignment_id
        )
    ) is None
    assert db_session.scalar(
        select(Carton.id).where(Carton.id == carton_id)
    ) == carton_id
