"""Deterministic physical carton placement inside warehouse locations."""

from dataclasses import dataclass
from decimal import Decimal
from itertools import product


PERCENT_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class ContainerDimensions:
    width_cm: Decimal
    depth_cm: Decimal
    height_cm: Decimal

    def __post_init__(self) -> None:
        if min(self.width_cm, self.depth_cm, self.height_cm) <= 0:
            raise ValueError("Container dimensions must be positive")

    @property
    def volume_cm3(self) -> Decimal:
        return self.width_cm * self.depth_cm * self.height_cm


@dataclass(frozen=True)
class CartonDimensions:
    length_cm: Decimal
    width_cm: Decimal
    height_cm: Decimal

    def __post_init__(self) -> None:
        if min(self.length_cm, self.width_cm, self.height_cm) <= 0:
            raise ValueError("Carton dimensions must be positive")

    @property
    def volume_cm3(self) -> Decimal:
        return self.length_cm * self.width_cm * self.height_cm


@dataclass(frozen=True)
class PlacedCarton:
    carton_id: int
    position_x_cm: Decimal
    position_y_cm: Decimal
    position_z_cm: Decimal
    occupied_width_cm: Decimal
    occupied_depth_cm: Decimal
    occupied_height_cm: Decimal
    rotation_degrees: int

    def __post_init__(self) -> None:
        if self.carton_id <= 0:
            raise ValueError("carton_id must be positive")
        if min(
            self.position_x_cm,
            self.position_y_cm,
            self.position_z_cm,
        ) < 0:
            raise ValueError("Placement coordinates cannot be negative")
        if min(
            self.occupied_width_cm,
            self.occupied_depth_cm,
            self.occupied_height_cm,
        ) <= 0:
            raise ValueError("Occupied dimensions must be positive")
        if self.rotation_degrees not in (0, 90):
            raise ValueError("rotation_degrees must be 0 or 90")

    @property
    def volume_cm3(self) -> Decimal:
        return (
            self.occupied_width_cm
            * self.occupied_depth_cm
            * self.occupied_height_cm
        )


@dataclass(frozen=True)
class PlacementResult:
    position_x_cm: Decimal
    position_y_cm: Decimal
    position_z_cm: Decimal
    occupied_width_cm: Decimal
    occupied_depth_cm: Decimal
    occupied_height_cm: Decimal
    rotation_degrees: int

    def to_placed_carton(self, carton_id: int) -> PlacedCarton:
        return PlacedCarton(carton_id=carton_id, **self.__dict__)


def has_weight_capacity(
    used_weight_kg: Decimal | None,
    incoming_weight_kg: Decimal | None,
    max_weight_kg: Decimal | None,
) -> bool:
    """Unknown weight data is not treated as available capacity."""
    if (
        used_weight_kg is None
        or incoming_weight_kg is None
        or max_weight_kg is None
    ):
        return False
    return used_weight_kg + incoming_weight_kg <= max_weight_kg


def volume_utilization_percent(
    container: ContainerDimensions,
    placed_cartons: list[PlacedCarton],
) -> Decimal:
    used_volume = sum(
        (carton.volume_cm3 for carton in placed_cartons),
        start=Decimal("0"),
    )
    return ((used_volume / container.volume_cm3) * Decimal("100")).quantize(
        PERCENT_QUANTUM
    )


def find_placement(
    container: ContainerDimensions,
    carton: CartonDimensions,
    placed_cartons: list[PlacedCarton],
) -> PlacementResult | None:
    """Find the first supported, non-overlapping placement in deterministic order."""
    x_coordinates = {Decimal("0")}
    y_coordinates = {Decimal("0")}
    z_coordinates = {Decimal("0")}
    for placed in placed_cartons:
        x_coordinates.add(placed.position_x_cm + placed.occupied_width_cm)
        y_coordinates.add(placed.position_y_cm + placed.occupied_depth_cm)
        z_coordinates.add(placed.position_z_cm + placed.occupied_height_cm)

    candidates = sorted(
        product(x_coordinates, y_coordinates, z_coordinates),
        key=lambda point: (point[2], point[1], point[0]),
    )
    for position_x, position_y, position_z in candidates:
        for rotation, occupied_width, occupied_depth in _orientations(carton):
            result = PlacementResult(
                position_x_cm=position_x,
                position_y_cm=position_y,
                position_z_cm=position_z,
                occupied_width_cm=occupied_width,
                occupied_depth_cm=occupied_depth,
                occupied_height_cm=carton.height_cm,
                rotation_degrees=rotation,
            )
            if not _is_within_bounds(container, result):
                continue
            if any(_overlaps(result, placed) for placed in placed_cartons):
                continue
            if not _is_supported(result, placed_cartons):
                continue
            return result
    return None


def _orientations(
    carton: CartonDimensions,
) -> tuple[tuple[int, Decimal, Decimal], ...]:
    normal = (0, carton.length_cm, carton.width_cm)
    if carton.length_cm == carton.width_cm:
        return (normal,)
    return (normal, (90, carton.width_cm, carton.length_cm))


def _is_within_bounds(
    container: ContainerDimensions,
    placement: PlacementResult,
) -> bool:
    return (
        placement.position_x_cm + placement.occupied_width_cm
        <= container.width_cm
        and placement.position_y_cm + placement.occupied_depth_cm
        <= container.depth_cm
        and placement.position_z_cm + placement.occupied_height_cm
        <= container.height_cm
    )


def _overlaps(
    candidate: PlacementResult,
    placed: PlacedCarton,
) -> bool:
    separated = (
        candidate.position_x_cm + candidate.occupied_width_cm
        <= placed.position_x_cm
        or placed.position_x_cm + placed.occupied_width_cm
        <= candidate.position_x_cm
        or candidate.position_y_cm + candidate.occupied_depth_cm
        <= placed.position_y_cm
        or placed.position_y_cm + placed.occupied_depth_cm
        <= candidate.position_y_cm
        or candidate.position_z_cm + candidate.occupied_height_cm
        <= placed.position_z_cm
        or placed.position_z_cm + placed.occupied_height_cm
        <= candidate.position_z_cm
    )
    return not separated


def _is_supported(
    candidate: PlacementResult,
    placed_cartons: list[PlacedCarton],
) -> bool:
    if candidate.position_z_cm == 0:
        return True

    candidate_right = candidate.position_x_cm + candidate.occupied_width_cm
    candidate_back = candidate.position_y_cm + candidate.occupied_depth_cm
    return any(
        placed.position_z_cm + placed.occupied_height_cm
        == candidate.position_z_cm
        and placed.position_x_cm <= candidate.position_x_cm
        and placed.position_x_cm + placed.occupied_width_cm >= candidate_right
        and placed.position_y_cm <= candidate.position_y_cm
        and placed.position_y_cm + placed.occupied_depth_cm >= candidate_back
        for placed in placed_cartons
    )
