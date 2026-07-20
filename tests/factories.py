"""Fiziksel depo testleri icin ortak veri yardimcilari."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import WarehouseRack


def create_warehouse_rack(
    session: Session,
    *,
    aisle: str = "TEST-A001",
    bay: str = "B001",
    level_count: int = 2,
    slots_per_level: int = 2,
    usable_slot_width_cm: Decimal = Decimal("100.00"),
    usable_depth_cm: Decimal = Decimal("80.00"),
    level_clear_height_cm: Decimal = Decimal("60.00"),
    frame_thickness_cm: Decimal = Decimal("5.00"),
    is_active: bool = True,
) -> WarehouseRack:
    """Test oturumunda sabit sinirlara sahip fiziksel bir raf olusturur."""
    normalized_aisle = aisle.strip().upper()
    normalized_bay = bay.strip().upper()
    existing_rack = session.scalar(
        select(WarehouseRack).where(
            WarehouseRack.aisle == normalized_aisle,
            WarehouseRack.bay == normalized_bay,
        )
    )
    if existing_rack is not None:
        return existing_rack

    width_cm = (
        usable_slot_width_cm * slots_per_level
        + frame_thickness_cm * (slots_per_level + 1)
    )
    rack = WarehouseRack(
        aisle=normalized_aisle,
        bay=normalized_bay,
        width_cm=width_cm,
        depth_cm=usable_depth_cm + frame_thickness_cm * 2,
        level_clear_height_cm=level_clear_height_cm,
        level_count=level_count,
        slots_per_level=slots_per_level,
        frame_thickness_cm=frame_thickness_cm,
        is_active=is_active,
    )
    session.add(rack)
    session.flush()
    return rack


def carton_type_dimensions(
    *,
    inner_length_cm: Decimal = Decimal("40.00"),
    inner_width_cm: Decimal = Decimal("30.00"),
    inner_height_cm: Decimal = Decimal("25.00"),
    wall_allowance_cm: Decimal = Decimal("2.00"),
) -> dict[str, str]:
    """JSON payloadlari icin fiziksel olarak gecerli koli olculeri dondurur."""
    return {
        "inner_length_cm": str(inner_length_cm),
        "inner_width_cm": str(inner_width_cm),
        "inner_height_cm": str(inner_height_cm),
        "outer_length_cm": str(inner_length_cm + wall_allowance_cm),
        "outer_width_cm": str(inner_width_cm + wall_allowance_cm),
        "outer_height_cm": str(inner_height_cm + wall_allowance_cm),
    }
