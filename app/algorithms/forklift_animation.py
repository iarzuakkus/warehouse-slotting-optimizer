"""Deterministic material-handling animation timeline construction."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


EquipmentType = Literal["cart", "pallet_jack", "forklift"]
HandlingEventType = Literal[
    "pickup",
    "dropoff",
    "staging_pickup",
    "staging_dropoff",
]
AnimationEventType = Literal[
    "travel",
    "pickup",
    "dropoff",
    "staging_pickup",
    "staging_dropoff",
]

DISTANCE_QUANTUM = Decimal("0.01")
TIME_QUANTUM = Decimal("0.01")
EQUIPMENT_SPEED_M_PER_SECOND: dict[EquipmentType, Decimal] = {
    "cart": Decimal("1.40"),
    "pallet_jack": Decimal("1.20"),
    "forklift": Decimal("2.50"),
}


@dataclass(frozen=True)
class AnimationRoutePoint:
    node_id: str
    x_m: Decimal
    y_m: Decimal
    z_m: Decimal = Decimal("0")
    distance_from_previous_m: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("Animation route node id cannot be empty")
        if self.z_m < 0 or self.distance_from_previous_m < 0:
            raise ValueError(
                "Animation route height and distance cannot be negative"
            )


@dataclass(frozen=True)
class AnimationRouteLeg:
    points: tuple[AnimationRoutePoint, ...]

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("Animation route leg must contain a point")
        if self.points[0].distance_from_previous_m != 0:
            raise ValueError(
                "First animation route point distance must be zero"
            )

    @property
    def distance_m(self) -> Decimal:
        return sum(
            (
                point.distance_from_previous_m
                for point in self.points[1:]
            ),
            start=Decimal("0"),
        )


@dataclass(frozen=True)
class AnimationStop:
    type: HandlingEventType
    location_id: int
    carton_ids: tuple[int, ...]
    route_from_previous: AnimationRouteLeg

    def __post_init__(self) -> None:
        if self.location_id <= 0:
            raise ValueError("Animation stop location id must be positive")
        if not self.carton_ids or any(
            carton_id <= 0 for carton_id in self.carton_ids
        ):
            raise ValueError(
                "Animation stop must contain positive carton ids"
            )


@dataclass(frozen=True)
class AnimationWaypoint:
    sequence: int
    node_id: str
    x_m: Decimal
    y_m: Decimal
    z_m: Decimal
    cumulative_distance_m: Decimal
    elapsed_seconds: Decimal


@dataclass(frozen=True)
class AnimationEvent:
    sequence: int
    type: AnimationEventType
    start_seconds: Decimal
    end_seconds: Decimal
    location_id: int | None
    carton_ids: tuple[int, ...]
    waypoints: tuple[AnimationWaypoint, ...]


@dataclass(frozen=True)
class BatchAnimationTimeline:
    route_distance_m: Decimal
    estimated_duration_seconds: Decimal
    events: tuple[AnimationEvent, ...]


def build_batch_animation(
    *,
    equipment_type: EquipmentType,
    stops: list[AnimationStop],
    return_to_dispatch: AnimationRouteLeg,
    handling_seconds_per_carton: Decimal = Decimal("8"),
    initial_loaded_carton_ids: tuple[int, ...] = (),
) -> BatchAnimationTimeline:
    """Convert routed stops into a deterministic frontend animation."""
    if equipment_type not in EQUIPMENT_SPEED_M_PER_SECOND:
        raise ValueError(f"Unsupported equipment type: {equipment_type}")
    if not stops:
        raise ValueError("Batch animation must contain at least one stop")
    if handling_seconds_per_carton <= 0:
        raise ValueError("Handling duration must be positive")
    if any(
        carton_id <= 0 for carton_id in initial_loaded_carton_ids
    ):
        raise ValueError("Initially loaded carton ids must be positive")
    if len(initial_loaded_carton_ids) != len(
        set(initial_loaded_carton_ids)
    ):
        raise ValueError("Initially loaded carton ids must be unique")

    speed = EQUIPMENT_SPEED_M_PER_SECOND[equipment_type]
    events: list[AnimationEvent] = []
    loaded_cartons = list(initial_loaded_carton_ids)
    elapsed = Decimal("0")
    distance = Decimal("0")

    for stop in stops:
        travel_event, elapsed, distance = _build_travel_event(
            sequence=len(events) + 1,
            route=stop.route_from_previous,
            loaded_cartons=tuple(loaded_cartons),
            speed=speed,
            elapsed=elapsed,
            distance=distance,
        )
        if travel_event is not None:
            events.append(travel_event)

        handling_start = elapsed
        elapsed += (
            handling_seconds_per_carton * len(stop.carton_ids)
        )
        events.append(
            AnimationEvent(
                sequence=len(events) + 1,
                type=stop.type,
                start_seconds=handling_start.quantize(TIME_QUANTUM),
                end_seconds=elapsed.quantize(TIME_QUANTUM),
                location_id=stop.location_id,
                carton_ids=stop.carton_ids,
                waypoints=(),
            )
        )
        if stop.type in ("pickup", "staging_pickup"):
            for carton_id in stop.carton_ids:
                if carton_id not in loaded_cartons:
                    loaded_cartons.append(carton_id)
        else:
            removed = set(stop.carton_ids)
            loaded_cartons = [
                carton_id
                for carton_id in loaded_cartons
                if carton_id not in removed
            ]

    return_event, elapsed, distance = _build_travel_event(
        sequence=len(events) + 1,
        route=return_to_dispatch,
        loaded_cartons=tuple(loaded_cartons),
        speed=speed,
        elapsed=elapsed,
        distance=distance,
    )
    if return_event is not None:
        events.append(return_event)

    return BatchAnimationTimeline(
        route_distance_m=distance.quantize(DISTANCE_QUANTUM),
        estimated_duration_seconds=elapsed.quantize(TIME_QUANTUM),
        events=tuple(events),
    )


def _build_travel_event(
    *,
    sequence: int,
    route: AnimationRouteLeg,
    loaded_cartons: tuple[int, ...],
    speed: Decimal,
    elapsed: Decimal,
    distance: Decimal,
) -> tuple[AnimationEvent | None, Decimal, Decimal]:
    if route.distance_m == 0:
        return None, elapsed, distance

    start_seconds = elapsed
    waypoints: list[AnimationWaypoint] = []
    for point_sequence, point in enumerate(route.points, start=1):
        distance += point.distance_from_previous_m
        elapsed += point.distance_from_previous_m / speed
        waypoints.append(
            AnimationWaypoint(
                sequence=point_sequence,
                node_id=point.node_id,
                x_m=point.x_m,
                y_m=point.y_m,
                z_m=point.z_m,
                cumulative_distance_m=distance.quantize(
                    DISTANCE_QUANTUM
                ),
                elapsed_seconds=elapsed.quantize(TIME_QUANTUM),
            )
        )

    return (
        AnimationEvent(
            sequence=sequence,
            type="travel",
            start_seconds=start_seconds.quantize(TIME_QUANTUM),
            end_seconds=elapsed.quantize(TIME_QUANTUM),
            location_id=None,
            carton_ids=loaded_cartons,
            waypoints=tuple(waypoints),
        ),
        elapsed,
        distance,
    )
