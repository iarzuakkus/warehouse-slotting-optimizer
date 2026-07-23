"""Deterministic physical carton placement inside warehouse locations."""

from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations, product
from typing import Literal


PERCENT_QUANTUM = Decimal("0.01")
PhysicalPlacementErrorCode = Literal[
    "duplicate_carton",
    "out_of_bounds",
    "carton_overlap",
    "unsupported_carton",
]


class PhysicalPlacementValidationError(ValueError):
    """Raised when a set of physical carton placements is not feasible."""

    def __init__(
        self,
        code: PhysicalPlacementErrorCode,
        message: str,
        carton_ids: tuple[int, ...],
    ) -> None:
        super().__init__(message)
        self.code = code
        self.carton_ids = carton_ids


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


def build_placed_carton(
    *,
    carton_id: int,
    dimensions: CartonDimensions,
    position_x_cm: Decimal,
    position_y_cm: Decimal,
    position_z_cm: Decimal,
    rotation_degrees: int,
) -> PlacedCarton:
    """Build an AABB using the supported horizontal carton rotations."""
    if rotation_degrees == 0:
        occupied_width = dimensions.length_cm
        occupied_depth = dimensions.width_cm
    elif rotation_degrees == 90:
        occupied_width = dimensions.width_cm
        occupied_depth = dimensions.length_cm
    else:
        raise ValueError("rotation_degrees must be 0 or 90")
    return PlacedCarton(
        carton_id=carton_id,
        position_x_cm=position_x_cm,
        position_y_cm=position_y_cm,
        position_z_cm=position_z_cm,
        occupied_width_cm=occupied_width,
        occupied_depth_cm=occupied_depth,
        occupied_height_cm=dimensions.height_cm,
        rotation_degrees=rotation_degrees,
    )


def placements_overlap(
    first: PlacementResult | PlacedCarton,
    second: PlacementResult | PlacedCarton,
) -> bool:
    """Return whether two axis-aligned occupied volumes intersect."""
    separated = (
        first.position_x_cm + first.occupied_width_cm
        <= second.position_x_cm
        or second.position_x_cm + second.occupied_width_cm
        <= first.position_x_cm
        or first.position_y_cm + first.occupied_depth_cm
        <= second.position_y_cm
        or second.position_y_cm + second.occupied_depth_cm
        <= first.position_y_cm
        or first.position_z_cm + first.occupied_height_cm
        <= second.position_z_cm
        or second.position_z_cm + second.occupied_height_cm
        <= first.position_z_cm
    )
    return not separated


def is_within_container(
    container: ContainerDimensions,
    placement: PlacementResult | PlacedCarton,
) -> bool:
    """Return whether an occupied volume stays inside its location."""
    return (
        placement.position_x_cm >= 0
        and placement.position_y_cm >= 0
        and placement.position_z_cm >= 0
        and placement.position_x_cm + placement.occupied_width_cm
        <= container.width_cm
        and placement.position_y_cm + placement.occupied_depth_cm
        <= container.depth_cm
        and placement.position_z_cm + placement.occupied_height_cm
        <= container.height_cm
    )


def is_fully_supported(
    candidate: PlacementResult | PlacedCarton,
    placed_cartons: list[PlacedCarton],
) -> bool:
    """Require the complete base footprint to rest on floor or carton tops."""
    if candidate.position_z_cm == 0:
        return True

    candidate_left = candidate.position_x_cm
    candidate_right = candidate_left + candidate.occupied_width_cm
    candidate_front = candidate.position_y_cm
    candidate_back = candidate_front + candidate.occupied_depth_cm
    supporters = [
        placed
        for placed in placed_cartons
        if placed.carton_id != getattr(candidate, "carton_id", None)
        and placed.position_z_cm + placed.occupied_height_cm
        == candidate.position_z_cm
        and placed.position_x_cm < candidate_right
        and placed.position_x_cm + placed.occupied_width_cm > candidate_left
        and placed.position_y_cm < candidate_back
        and placed.position_y_cm + placed.occupied_depth_cm > candidate_front
    ]
    if not supporters:
        return False

    x_edges = {candidate_left, candidate_right}
    y_edges = {candidate_front, candidate_back}
    for supporter in supporters:
        x_edges.update(
            {
                max(candidate_left, supporter.position_x_cm),
                min(
                    candidate_right,
                    supporter.position_x_cm + supporter.occupied_width_cm,
                ),
            }
        )
        y_edges.update(
            {
                max(candidate_front, supporter.position_y_cm),
                min(
                    candidate_back,
                    supporter.position_y_cm + supporter.occupied_depth_cm,
                ),
            }
        )

    ordered_x = sorted(x_edges)
    ordered_y = sorted(y_edges)
    return all(
        any(
            supporter.position_x_cm <= left
            and supporter.position_x_cm + supporter.occupied_width_cm >= right
            and supporter.position_y_cm <= front
            and supporter.position_y_cm + supporter.occupied_depth_cm >= back
            for supporter in supporters
        )
        for left, right in zip(ordered_x, ordered_x[1:])
        for front, back in zip(ordered_y, ordered_y[1:])
        if right > left and back > front
    )


def validate_placements(
    container: ContainerDimensions,
    placed_cartons: list[PlacedCarton],
) -> None:
    """Validate uniqueness, bounds, collision, and full physical support."""
    carton_ids = [carton.carton_id for carton in placed_cartons]
    duplicate_ids = sorted(
        carton_id
        for carton_id in set(carton_ids)
        if carton_ids.count(carton_id) > 1
    )
    if duplicate_ids:
        raise PhysicalPlacementValidationError(
            "duplicate_carton",
            "A carton appears more than once in the physical scene",
            tuple(duplicate_ids),
        )

    for carton in placed_cartons:
        if not is_within_container(container, carton):
            raise PhysicalPlacementValidationError(
                "out_of_bounds",
                f"Carton {carton.carton_id} exceeds location boundaries",
                (carton.carton_id,),
            )

    for first, second in combinations(placed_cartons, 2):
        if placements_overlap(first, second):
            raise PhysicalPlacementValidationError(
                "carton_overlap",
                f"Cartons {first.carton_id} and {second.carton_id} overlap",
                (first.carton_id, second.carton_id),
            )

    for carton in placed_cartons:
        if not is_fully_supported(carton, placed_cartons):
            raise PhysicalPlacementValidationError(
                "unsupported_carton",
                f"Carton {carton.carton_id} is not fully supported",
                (carton.carton_id,),
            )


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
            if not is_within_container(container, result):
                continue
            if any(
                placements_overlap(result, placed)
                for placed in placed_cartons
            ):
                continue
            if not is_fully_supported(result, placed_cartons):
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
