"""Deterministic, in-memory slotting optimization for simulation scenarios."""

from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
from typing import Literal, Mapping

from app.algorithms.carton_placement import (
    CartonDimensions,
    ContainerDimensions,
    PlacedCarton,
    PlacementResult,
    find_placement,
    has_weight_capacity,
)


ABCClass = Literal["A", "B", "C"]
AssignmentStatus = Literal["placed", "unplaced"]
PERCENT = Decimal("100")
PERCENT_QUANTUM = Decimal("0.01")
SCORE_QUANTUM = Decimal("0.000001")


@dataclass(frozen=True)
class SlottingWeights:
    same_sku_location: Decimal = Decimal("8")
    same_rack: Decimal = Decimal("4")
    nearby_aisle: Decimal = Decimal("2")
    lower_level_for_heavy: Decimal = Decimal("5")
    dispatch_distance: Decimal = Decimal("7")
    co_shipment_proximity: Decimal = Decimal("3")
    location_consolidation: Decimal = Decimal("4")
    split_sku: Decimal = Decimal("6")
    moves: Decimal = Decimal("5")
    volume_utilization: Decimal = Decimal("4")

    def __post_init__(self) -> None:
        values = tuple(self.__dict__.values())
        if any(value < 0 for value in values):
            raise ValueError("Slotting objective weights cannot be negative")
        if not any(value > 0 for value in values):
            raise ValueError("At least one slotting objective must be active")


@dataclass(frozen=True)
class SlottingConfig:
    seed: int = 0
    group_same_sku: bool = True
    prefer_lower_levels_for_heavy_cartons: bool = True
    minimize_dispatch_distance: bool = True
    minimize_moves: bool = True
    improve_volume_utilization: bool = True
    heavy_carton_threshold_kg: Decimal = Decimal("25")
    weights: SlottingWeights = field(default_factory=SlottingWeights)

    def __post_init__(self) -> None:
        if self.seed < 0:
            raise ValueError("seed cannot be negative")
        if self.heavy_carton_threshold_kg <= 0:
            raise ValueError("heavy_carton_threshold_kg must be positive")


@dataclass(frozen=True)
class SlottingLocation:
    id: int
    aisle: str
    bay: str
    level: str
    slot: str
    aisle_rank: int
    level_rank: int
    is_active: bool
    dimensions: ContainerDimensions
    max_weight_kg: Decimal | None
    dispatch_distance_m: Decimal
    fixed_cartons: tuple[PlacedCarton, ...] = ()
    fixed_weight_kg: Decimal | None = Decimal("0")
    fixed_skus: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError("location id must be positive")
        if self.aisle_rank <= 0 or self.level_rank <= 0:
            raise ValueError("location ranks must be positive")
        if self.dispatch_distance_m < 0:
            raise ValueError("dispatch distance cannot be negative")
        if self.fixed_weight_kg is not None and self.fixed_weight_kg < 0:
            raise ValueError("fixed location weight cannot be negative")

    @property
    def rack_key(self) -> tuple[str, str]:
        return self.aisle, self.bay


@dataclass(frozen=True)
class SlottingCarton:
    id: int
    carton_number: str
    product_id: int
    sku: str
    dimensions: CartonDimensions
    weight_kg: Decimal | None
    current_location_id: int | None
    current_position_x_cm: Decimal | None
    current_position_y_cm: Decimal | None
    current_position_z_cm: Decimal | None
    current_rotation_degrees: int | None
    abc_class: ABCClass | None = None
    co_shipped_skus: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.id <= 0 or self.product_id <= 0:
            raise ValueError("carton and product ids must be positive")
        if not self.carton_number or not self.sku:
            raise ValueError("carton_number and sku cannot be empty")
        if self.weight_kg is not None and self.weight_kg < 0:
            raise ValueError("carton weight cannot be negative")
        coordinates = (
            self.current_position_x_cm,
            self.current_position_y_cm,
            self.current_position_z_cm,
            self.current_rotation_degrees,
        )
        if any(value is None for value in coordinates) and any(
            value is not None for value in coordinates
        ):
            raise ValueError("current carton placement must be complete")
        if self.current_rotation_degrees not in (None, 0, 90):
            raise ValueError("current rotation must be 0, 90, or null")


@dataclass(frozen=True)
class SlottingProposal:
    carton_id: int
    carton_number: str
    product_id: int
    sku: str
    result_status: AssignmentStatus
    from_location_id: int | None
    to_location_id: int | None
    from_position_x_cm: Decimal | None
    from_position_y_cm: Decimal | None
    from_position_z_cm: Decimal | None
    from_rotation_degrees: int | None
    proposed_position_x_cm: Decimal | None
    proposed_position_y_cm: Decimal | None
    proposed_position_z_cm: Decimal | None
    proposed_rotation_degrees: int | None
    score: Decimal | None
    reasons: tuple[str, ...]
    unplaced_reason: str | None = None

    @property
    def requires_move(self) -> bool:
        if self.result_status == "unplaced":
            return False
        return (
            self.from_location_id != self.to_location_id
            or self.from_position_x_cm != self.proposed_position_x_cm
            or self.from_position_y_cm != self.proposed_position_y_cm
            or self.from_position_z_cm != self.proposed_position_z_cm
            or self.from_rotation_degrees != self.proposed_rotation_degrees
        )


@dataclass(frozen=True)
class SlottingMetrics:
    total_dispatch_distance: Decimal
    average_dispatch_distance: Decimal
    weight_utilization_percent: Decimal | None
    volume_utilization_percent: Decimal
    used_location_count: int
    split_sku_count: int
    moved_carton_count: int
    unplaced_carton_count: int
    objective_score: Decimal


@dataclass(frozen=True)
class SlottingResult:
    proposals: tuple[SlottingProposal, ...]
    moves: tuple[SlottingProposal, ...]
    metrics: SlottingMetrics


@dataclass
class _LocationState:
    location: SlottingLocation
    placed_cartons: list[PlacedCarton]
    used_weight_kg: Decimal | None
    skus: set[str]


@dataclass(frozen=True)
class _EvaluatedLocation:
    state: _LocationState
    placement: PlacementResult
    score: Decimal
    reasons: tuple[str, ...]
    tie_breaker: str


def optimize_slotting(
    locations: list[SlottingLocation],
    cartons: list[SlottingCarton],
    config: SlottingConfig,
) -> SlottingResult:
    """Build an alternative placement without mutating the source layout."""
    _validate_unique_ids(locations, cartons)
    states = {
        location.id: _LocationState(
            location=location,
            placed_cartons=list(location.fixed_cartons),
            used_weight_kg=location.fixed_weight_kg,
            skus=set(location.fixed_skus),
        )
        for location in locations
        if location.is_active
    }
    location_by_id = {location.id: location for location in locations}
    maximum_level = max(
        (location.level_rank for location in locations),
        default=1,
    )

    proposals: list[SlottingProposal] = []
    for carton in _ordered_cartons(cartons, config.seed):
        proposal = _place_carton(
            carton,
            states,
            location_by_id,
            maximum_level,
            config,
        )
        proposals.append(proposal)

    moves = tuple(
        proposal
        for proposal in proposals
        if proposal.result_status == "unplaced" or proposal.requires_move
    )
    metrics = _calculate_metrics(states, proposals)
    return SlottingResult(
        proposals=tuple(proposals),
        moves=moves,
        metrics=metrics,
    )


def _validate_unique_ids(
    locations: list[SlottingLocation],
    cartons: list[SlottingCarton],
) -> None:
    location_ids = [location.id for location in locations]
    carton_ids = [carton.id for carton in cartons]
    if len(location_ids) != len(set(location_ids)):
        raise ValueError("location ids must be unique")
    if len(carton_ids) != len(set(carton_ids)):
        raise ValueError("carton ids must be unique")


def _ordered_cartons(
    cartons: list[SlottingCarton],
    seed: int,
) -> list[SlottingCarton]:
    abc_rank = {"A": 0, "B": 1, "C": 2, None: 3}
    return sorted(
        cartons,
        key=lambda carton: (
            -(carton.weight_kg or Decimal("-1")),
            abc_rank[carton.abc_class],
            carton.sku,
            _stable_tie_breaker(seed, "carton", carton.id),
            carton.id,
        ),
    )


def _place_carton(
    carton: SlottingCarton,
    states: Mapping[int, _LocationState],
    location_by_id: Mapping[int, SlottingLocation],
    maximum_level: int,
    config: SlottingConfig,
) -> SlottingProposal:
    if carton.weight_kg is None:
        return _unplaced(carton, "unknown_carton_weight")
    if not states:
        return _unplaced(carton, "no_active_location")

    evaluated: list[_EvaluatedLocation] = []
    for state in states.values():
        location = state.location
        if not has_weight_capacity(
            state.used_weight_kg,
            carton.weight_kg,
            location.max_weight_kg,
        ):
            continue
        placement = find_placement(
            location.dimensions,
            carton.dimensions,
            state.placed_cartons,
        )
        if placement is None:
            continue
        score, reasons = _score_location(
            carton,
            state,
            location_by_id,
            maximum_level,
            placement,
            config,
        )
        evaluated.append(
            _EvaluatedLocation(
                state=state,
                placement=placement,
                score=score,
                reasons=reasons,
                tie_breaker=_stable_tie_breaker(
                    config.seed,
                    "location",
                    carton.id,
                    location.id,
                ),
            )
        )

    if not evaluated:
        return _unplaced(carton, "no_location_satisfies_hard_constraints")

    selected = min(
        evaluated,
        key=lambda item: (
            -item.score,
            item.tie_breaker,
            item.state.location.aisle_rank,
            item.state.location.bay,
            item.state.location.level_rank,
            item.state.location.slot,
            item.state.location.id,
        ),
    )
    state = selected.state
    state.placed_cartons.append(
        selected.placement.to_placed_carton(carton.id)
    )
    if state.used_weight_kg is not None:
        state.used_weight_kg += carton.weight_kg
    state.skus.add(carton.sku)

    return SlottingProposal(
        carton_id=carton.id,
        carton_number=carton.carton_number,
        product_id=carton.product_id,
        sku=carton.sku,
        result_status="placed",
        from_location_id=carton.current_location_id,
        to_location_id=state.location.id,
        from_position_x_cm=carton.current_position_x_cm,
        from_position_y_cm=carton.current_position_y_cm,
        from_position_z_cm=carton.current_position_z_cm,
        from_rotation_degrees=carton.current_rotation_degrees,
        proposed_position_x_cm=selected.placement.position_x_cm,
        proposed_position_y_cm=selected.placement.position_y_cm,
        proposed_position_z_cm=selected.placement.position_z_cm,
        proposed_rotation_degrees=selected.placement.rotation_degrees,
        score=selected.score.quantize(SCORE_QUANTUM),
        reasons=selected.reasons,
    )


def _score_location(
    carton: SlottingCarton,
    state: _LocationState,
    location_by_id: Mapping[int, SlottingLocation],
    maximum_level: int,
    placement: PlacementResult,
    config: SlottingConfig,
) -> tuple[Decimal, tuple[str, ...]]:
    location = state.location
    weights = config.weights
    score = Decimal("0")
    reasons: list[str] = []
    current = location_by_id.get(carton.current_location_id)

    if config.minimize_moves and location.id == carton.current_location_id:
        score += weights.moves

    if config.group_same_sku and carton.sku in state.skus:
        score += weights.same_sku_location + weights.split_sku
        reasons.append("same_sku_grouped")

    if current is not None and current.rack_key == location.rack_key:
        score += weights.same_rack
        if current.id != location.id:
            reasons.append("same_rack_preferred")

    if current is not None:
        aisle_difference = abs(current.aisle_rank - location.aisle_rank)
        score -= Decimal(aisle_difference) * weights.nearby_aisle
        if aisle_difference == 0 and current.rack_key != location.rack_key:
            reasons.append("same_aisle_preferred")

    is_heavy = carton.weight_kg >= config.heavy_carton_threshold_kg
    if config.prefer_lower_levels_for_heavy_cartons and is_heavy:
        lower_level_bonus = maximum_level - location.level_rank + 1
        score += Decimal(lower_level_bonus) * weights.lower_level_for_heavy
        reasons.append("heavy_carton_lower_level")

    if config.minimize_dispatch_distance:
        demand_multiplier = {
            "A": Decimal("3"),
            "B": Decimal("2"),
            "C": Decimal("1"),
            None: Decimal("1"),
        }[carton.abc_class]
        score -= (
            location.dispatch_distance_m
            * weights.dispatch_distance
            * demand_multiplier
        )
        if (
            current is not None
            and location.dispatch_distance_m < current.dispatch_distance_m
        ):
            reasons.append("dispatch_distance_reduced")

    related_skus = state.skus.intersection(carton.co_shipped_skus)
    if related_skus:
        score += weights.co_shipment_proximity * len(related_skus)
        reasons.append("co_shipped_products_grouped")

    if state.placed_cartons:
        score += weights.location_consolidation
        reasons.append("location_consolidated")

    if config.improve_volume_utilization:
        projected_volume = sum(
            (placed.volume_cm3 for placed in state.placed_cartons),
            start=placement.to_placed_carton(carton.id).volume_cm3,
        )
        projected_ratio = projected_volume / location.dimensions.volume_cm3
        score += projected_ratio * weights.volume_utilization

    if not reasons:
        reasons.append("best_feasible_location")
    return score, tuple(dict.fromkeys(reasons))


def _unplaced(carton: SlottingCarton, reason: str) -> SlottingProposal:
    return SlottingProposal(
        carton_id=carton.id,
        carton_number=carton.carton_number,
        product_id=carton.product_id,
        sku=carton.sku,
        result_status="unplaced",
        from_location_id=carton.current_location_id,
        to_location_id=None,
        from_position_x_cm=carton.current_position_x_cm,
        from_position_y_cm=carton.current_position_y_cm,
        from_position_z_cm=carton.current_position_z_cm,
        from_rotation_degrees=carton.current_rotation_degrees,
        proposed_position_x_cm=None,
        proposed_position_y_cm=None,
        proposed_position_z_cm=None,
        proposed_rotation_degrees=None,
        score=None,
        reasons=(reason,),
        unplaced_reason=reason,
    )


def _calculate_metrics(
    states: Mapping[int, _LocationState],
    proposals: list[SlottingProposal],
) -> SlottingMetrics:
    used_states = [state for state in states.values() if state.placed_cartons]
    placed_count = sum(len(state.placed_cartons) for state in used_states)
    total_dispatch_distance = sum(
        (
            state.location.dispatch_distance_m * len(state.placed_cartons)
            for state in used_states
        ),
        start=Decimal("0"),
    )
    average_dispatch_distance = (
        total_dispatch_distance / placed_count
        if placed_count
        else Decimal("0")
    )

    known_weight_capacity = all(
        state.location.max_weight_kg is not None
        and state.used_weight_kg is not None
        for state in states.values()
    )
    weight_utilization: Decimal | None = None
    if known_weight_capacity:
        total_weight = sum(
            (state.used_weight_kg or Decimal("0") for state in states.values()),
            start=Decimal("0"),
        )
        total_capacity = sum(
            (
                state.location.max_weight_kg or Decimal("0")
                for state in states.values()
            ),
            start=Decimal("0"),
        )
        if total_capacity > 0:
            weight_utilization = (
                total_weight / total_capacity * PERCENT
            ).quantize(PERCENT_QUANTUM)

    used_volume = sum(
        (
            placed.volume_cm3
            for state in states.values()
            for placed in state.placed_cartons
        ),
        start=Decimal("0"),
    )
    total_volume = sum(
        (state.location.dimensions.volume_cm3 for state in states.values()),
        start=Decimal("0"),
    )
    volume_utilization = (
        (used_volume / total_volume * PERCENT).quantize(PERCENT_QUANTUM)
        if total_volume > 0
        else Decimal("0")
    )

    sku_locations: dict[str, set[int]] = {}
    for state in states.values():
        for sku in state.skus:
            sku_locations.setdefault(sku, set()).add(state.location.id)

    moved_count = sum(
        proposal.result_status == "placed" and proposal.requires_move
        for proposal in proposals
    )
    unplaced_count = sum(
        proposal.result_status == "unplaced" for proposal in proposals
    )
    objective_score = sum(
        (
            proposal.score
            for proposal in proposals
            if proposal.score is not None
        ),
        start=Decimal("0"),
    ).quantize(SCORE_QUANTUM)
    return SlottingMetrics(
        total_dispatch_distance=total_dispatch_distance.quantize(
            PERCENT_QUANTUM
        ),
        average_dispatch_distance=average_dispatch_distance.quantize(
            PERCENT_QUANTUM
        ),
        weight_utilization_percent=weight_utilization,
        volume_utilization_percent=volume_utilization,
        used_location_count=len(used_states),
        split_sku_count=sum(
            len(location_ids) > 1 for location_ids in sku_locations.values()
        ),
        moved_carton_count=moved_count,
        unplaced_carton_count=unplaced_count,
        objective_score=objective_score,
    )


def _stable_tie_breaker(seed: int, *parts: object) -> str:
    value = ":".join(str(part) for part in (seed, *parts))
    return sha256(value.encode("utf-8")).hexdigest()
