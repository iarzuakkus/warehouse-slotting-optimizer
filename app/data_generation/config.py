"""Sentetik veri büyüklükleri ve üretim profilleri."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SyntheticDataProfile:
    name: str
    product_count: int
    aisle_count: int
    bays_per_aisle: int
    levels_per_bay: int
    slots_per_level: int
    carton_count: int
    historical_order_count: int
    pending_order_count: int
    min_lines_per_order: int = 1
    max_lines_per_order: int = 6
    batch_size: int = 1_000

    def __post_init__(self) -> None:
        numeric_values = (
            self.product_count,
            self.aisle_count,
            self.bays_per_aisle,
            self.levels_per_bay,
            self.slots_per_level,
            self.carton_count,
            self.historical_order_count,
            self.batch_size,
        )
        if any(value <= 0 for value in numeric_values):
            raise ValueError("Profile counts must be positive")
        if self.pending_order_count < 0:
            raise ValueError("pending_order_count cannot be negative")
        if self.min_lines_per_order > self.max_lines_per_order:
            raise ValueError("Minimum order lines cannot exceed maximum order lines")

    @property
    def location_count(self) -> int:
        return (
            self.aisle_count
            * self.bays_per_aisle
            * self.levels_per_bay
            * self.slots_per_level
        )


PROFILES: dict[str, SyntheticDataProfile] = {
    "smoke": SyntheticDataProfile(
        name="smoke",
        product_count=50,
        aisle_count=5,
        bays_per_aisle=5,
        levels_per_bay=2,
        slots_per_level=2,
        carton_count=200,
        historical_order_count=500,
        pending_order_count=25,
        batch_size=250,
    ),
    "small": SyntheticDataProfile(
        name="small",
        product_count=250,
        aisle_count=5,
        bays_per_aisle=10,
        levels_per_bay=5,
        slots_per_level=2,
        carton_count=1_500,
        historical_order_count=10_000,
        pending_order_count=250,
    ),
    "medium": SyntheticDataProfile(
        name="medium",
        product_count=1_000,
        aisle_count=20,
        bays_per_aisle=10,
        levels_per_bay=5,
        slots_per_level=2,
        carton_count=10_000,
        historical_order_count=100_000,
        pending_order_count=2_000,
    ),
    "large": SyntheticDataProfile(
        name="large",
        product_count=5_000,
        aisle_count=20,
        bays_per_aisle=25,
        levels_per_bay=5,
        slots_per_level=4,
        carton_count=100_000,
        historical_order_count=1_000_000,
        pending_order_count=10_000,
        max_lines_per_order=8,
        batch_size=5_000,
    ),
}


def get_profile(name: str) -> SyntheticDataProfile:
    normalized_name = name.strip().lower()
    try:
        return PROFILES[normalized_name]
    except KeyError as exc:
        available = ", ".join(PROFILES)
        raise ValueError(
            f"Unknown profile '{name}'. Available profiles: {available}"
        ) from exc
