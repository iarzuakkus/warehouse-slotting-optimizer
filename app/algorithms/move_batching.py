"""Deterministic operational batching for simulated carton movements."""

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from app.algorithms.carton_placement import PlacedCarton, placements_overlap


EquipmentType = Literal["cart", "pallet_jack", "forklift"]
StopType = Literal["pickup", "dropoff"]
ValidationCode = Literal[
    "max_batch_weight_exceeded",
    "max_batch_volume_exceeded",
]
LocationSortKey = tuple[int, int, int, int]
PERCENT = Decimal("100")
PERCENT_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class MoveBatchLimits:
    equipment_type: EquipmentType
    max_weight_kg: Decimal
    max_volume_m3: Decimal
    max_cartons: int

    def __post_init__(self) -> None:
        if self.max_weight_kg <= 0 or self.max_volume_m3 <= 0:
            raise ValueError("Batch weight and volume limits must be positive")
        if self.max_cartons <= 0:
            raise ValueError("Batch carton limit must be positive")


@dataclass(frozen=True)
class MoveBatchCandidate:
    move_sequence: int
    carton_id: int
    carton_number: str
    sku: str
    weight_kg: Decimal
    volume_m3: Decimal
    from_location_id: int | None
    to_location_id: int
    from_location_key: LocationSortKey | None
    to_location_key: LocationSortKey
    individual_distance_m: Decimal
    individual_duration_seconds: Decimal
    source_placement: PlacedCarton | None = None
    target_placement: PlacedCarton | None = None

    def __post_init__(self) -> None:
        if self.move_sequence <= 0 or self.carton_id <= 0:
            raise ValueError("Move sequence and carton id must be positive")
        if not self.carton_number or not self.sku:
            raise ValueError("Carton number and SKU cannot be empty")
        if self.weight_kg < 0:
            raise ValueError("Carton weight cannot be negative")
        if self.volume_m3 <= 0:
            raise ValueError("Carton volume must be positive")
        if self.to_location_id <= 0:
            raise ValueError("Target location id must be positive")
        if self.from_location_id is not None and self.from_location_id <= 0:
            raise ValueError("Source location id must be positive")
        if (
            self.individual_distance_m < 0
            or self.individual_duration_seconds < 0
        ):
            raise ValueError("Movement distance and duration cannot be negative")
        if any(
            placement is not None and placement.carton_id != self.carton_id
            for placement in (
                self.source_placement,
                self.target_placement,
            )
        ):
            raise ValueError("Physical placements must belong to the move carton")


@dataclass(frozen=True)
class PlannedBatchStop:
    sequence: int
    type: StopType
    location_id: int
    carton_ids: tuple[int, ...]


@dataclass(frozen=True)
class MoveBatchValidation:
    move_sequence: int
    carton_id: int
    code: ValidationCode
    message: str


@dataclass(frozen=True)
class PlannedMoveBatch:
    sequence: int
    equipment_type: EquipmentType
    items: tuple[MoveBatchCandidate, ...]
    total_weight_kg: Decimal
    total_volume_m3: Decimal
    capacity_utilization_percent: Decimal
    stops: tuple[PlannedBatchStop, ...]
    reasons: tuple[str, ...]
    requires_staging_buffer: bool
    staged_items: tuple[MoveBatchCandidate, ...] = ()
    finalized_items: tuple[MoveBatchCandidate, ...] = ()

    @property
    def move_sequences(self) -> tuple[int, ...]:
        return tuple(item.move_sequence for item in self.items)

    @property
    def staged_move_sequences(self) -> tuple[int, ...]:
        return tuple(item.move_sequence for item in self.staged_items)

    @property
    def finalized_move_sequences(self) -> tuple[int, ...]:
        return tuple(item.move_sequence for item in self.finalized_items)

    @property
    def operational_items(self) -> tuple[MoveBatchCandidate, ...]:
        return self.items + self.finalized_items


@dataclass(frozen=True)
class MoveBatchPlan:
    batches: tuple[PlannedMoveBatch, ...]
    unbatched_items: tuple[MoveBatchCandidate, ...]
    validation_errors: tuple[MoveBatchValidation, ...]
    requires_staging_buffer: bool
    staging_move_sequences: tuple[int, ...]


def plan_move_batches(
    moves: list[MoveBatchCandidate],
    limits: MoveBatchLimits,
    seed: int,
) -> MoveBatchPlan:
    """Group placed moves once while respecting capacity and dependencies."""
    if seed < 0:
        raise ValueError("seed cannot be negative")
    _validate_unique_moves(moves)

    eligible: dict[int, MoveBatchCandidate] = {}
    unbatched: list[MoveBatchCandidate] = []
    validation_errors: list[MoveBatchValidation] = []
    for move in moves:
        errors = _capacity_validation(move, limits)
        if errors:
            unbatched.append(move)
            validation_errors.extend(errors)
        else:
            eligible[move.move_sequence] = move

    source_release_dependencies, target_support_dependencies = (
        _build_dependency_groups(list(eligible.values()))
    )
    dependencies = {
        sequence: (
            source_release_dependencies[sequence]
            | target_support_dependencies[sequence]
        )
        for sequence in source_release_dependencies
    }
    cycle_components = _find_cycle_components(dependencies)
    staged_moves = [
        _select_staging_move(component, eligible, seed)
        for component in cycle_components
    ]
    staged_sequences = {
        move.move_sequence for move in staged_moves
    }
    cycle_sequences = {
        sequence
        for component in cycle_components
        for sequence in component
    }
    remaining = set(eligible) - staged_sequences
    source_released: set[int] = set(staged_sequences)
    target_placed: set[int] = set()
    pending_finalize = set(staged_sequences)
    batches: list[PlannedMoveBatch] = []

    for staged_move in staged_moves:
        batches.append(
            _build_batch(
                sequence=len(batches) + 1,
                items=[staged_move],
                limits=limits,
                cycle_sequences=cycle_sequences,
                dependencies=dependencies,
                staged_items=[staged_move],
            )
        )

    while remaining or pending_finalize:
        ready_to_finalize = sorted(
            sequence
            for sequence in pending_finalize
            if source_release_dependencies[sequence].issubset(source_released)
            and target_support_dependencies[sequence].issubset(target_placed)
        )
        if ready_to_finalize:
            sequence = ready_to_finalize[0]
            staged_move = eligible[sequence]
            batches.append(
                _build_batch(
                    sequence=len(batches) + 1,
                    items=[],
                    limits=limits,
                    cycle_sequences=cycle_sequences,
                    dependencies=dependencies,
                    finalized_items=[staged_move],
                )
            )
            pending_finalize.remove(sequence)
            target_placed.add(sequence)
            continue

        selected: list[MoveBatchCandidate] = []
        selected_sequences: set[int] = set()

        while True:
            ready = [
                eligible[sequence]
                for sequence in remaining - selected_sequences
                if source_release_dependencies[sequence].issubset(
                    source_released | selected_sequences
                )
                and target_support_dependencies[sequence].issubset(
                    target_placed | selected_sequences
                )
            ]
            if not ready:
                break

            fitting = [
                move
                for move in ready
                if _fits_batch(selected, move, limits)
            ]
            if not fitting:
                break
            anchor = selected[-1] if selected else None
            chosen = min(
                fitting,
                key=lambda move: _grouping_priority(
                    move,
                    anchor,
                    seed,
                ),
            )
            selected.append(chosen)
            selected_sequences.add(chosen.move_sequence)
            if len(selected) == limits.max_cartons:
                break

        if not selected:
            blocked_sequences = remaining | pending_finalize
            unreleased_dependencies = {
                dependency
                for sequence in blocked_sequences
                for dependency in source_release_dependencies[sequence]
                if dependency not in source_released
            }
            staging_candidates = remaining.intersection(
                unreleased_dependencies
            )
            if not staging_candidates:
                raise RuntimeError(
                    "Physical move batch dependencies cannot be resolved"
                )
            staged_move = _select_staging_move(
                staging_candidates,
                eligible,
                seed,
            )
            sequence = staged_move.move_sequence
            staged_moves.append(staged_move)
            staged_sequences.add(sequence)
            cycle_sequences.add(sequence)
            remaining.remove(sequence)
            source_released.add(sequence)
            pending_finalize.add(sequence)
            batches.append(
                _build_batch(
                    sequence=len(batches) + 1,
                    items=[staged_move],
                    limits=limits,
                    cycle_sequences=cycle_sequences,
                    dependencies=dependencies,
                    staged_items=[staged_move],
                )
            )
            continue

        source_released.update(selected_sequences)
        target_placed.update(selected_sequences)
        remaining.difference_update(selected_sequences)
        batches.append(
            _build_batch(
                sequence=len(batches) + 1,
                items=selected,
                limits=limits,
                cycle_sequences=cycle_sequences,
                dependencies=dependencies,
            )
        )

    _validate_plan_completeness(
        eligible_sequences=set(eligible),
        batches=batches,
    )
    ordered_unbatched = tuple(
        sorted(unbatched, key=lambda move: move.move_sequence)
    )
    return MoveBatchPlan(
        batches=tuple(batches),
        unbatched_items=ordered_unbatched,
        validation_errors=tuple(
            sorted(
                validation_errors,
                key=lambda error: (
                    error.move_sequence,
                    error.code,
                ),
            )
        ),
        requires_staging_buffer=bool(staged_moves),
        staging_move_sequences=tuple(
            move.move_sequence for move in staged_moves
        ),
    )


def _validate_unique_moves(moves: list[MoveBatchCandidate]) -> None:
    sequences = [move.move_sequence for move in moves]
    carton_ids = [move.carton_id for move in moves]
    if len(sequences) != len(set(sequences)):
        raise ValueError("Move sequences must be unique")
    if len(carton_ids) != len(set(carton_ids)):
        raise ValueError("A carton can appear in the move plan only once")


def _capacity_validation(
    move: MoveBatchCandidate,
    limits: MoveBatchLimits,
) -> list[MoveBatchValidation]:
    validations: list[MoveBatchValidation] = []
    if move.weight_kg > limits.max_weight_kg:
        validations.append(
            MoveBatchValidation(
                move_sequence=move.move_sequence,
                carton_id=move.carton_id,
                code="max_batch_weight_exceeded",
                message=(
                    f"Carton weight {move.weight_kg} kg exceeds "
                    f"{limits.max_weight_kg} kg batch limit"
                ),
            )
        )
    if move.volume_m3 > limits.max_volume_m3:
        validations.append(
            MoveBatchValidation(
                move_sequence=move.move_sequence,
                carton_id=move.carton_id,
                code="max_batch_volume_exceeded",
                message=(
                    f"Carton volume {move.volume_m3} m3 exceeds "
                    f"{limits.max_volume_m3} m3 batch limit"
                ),
            )
        )
    return validations


def _build_dependencies(
    moves: list[MoveBatchCandidate],
) -> dict[int, set[int]]:
    source_release_dependencies, target_support_dependencies = (
        _build_dependency_groups(moves)
    )
    return {
        sequence: (
            source_release_dependencies[sequence]
            | target_support_dependencies[sequence]
        )
        for sequence in source_release_dependencies
    }


def _build_dependency_groups(
    moves: list[MoveBatchCandidate],
) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    source_release_dependencies = {
        move.move_sequence: set() for move in moves
    }
    target_support_dependencies = {
        move.move_sequence: set() for move in moves
    }
    for incoming in moves:
        for outgoing in moves:
            if incoming.move_sequence == outgoing.move_sequence:
                continue
            if _target_is_blocked_by_source(incoming, outgoing):
                source_release_dependencies[incoming.move_sequence].add(
                    outgoing.move_sequence
                )
            if _source_carton_supports_other(outgoing, incoming):
                source_release_dependencies[outgoing.move_sequence].add(
                    incoming.move_sequence
                )
            if _target_carton_supports_other(outgoing, incoming):
                target_support_dependencies[incoming.move_sequence].add(
                    outgoing.move_sequence
                )
    return source_release_dependencies, target_support_dependencies


def _target_is_blocked_by_source(
    incoming: MoveBatchCandidate,
    outgoing: MoveBatchCandidate,
) -> bool:
    if (
        outgoing.from_location_id is None
        or incoming.to_location_id != outgoing.from_location_id
    ):
        return False
    if (
        incoming.target_placement is None
        or outgoing.source_placement is None
    ):
        return True
    return placements_overlap(
        incoming.target_placement,
        outgoing.source_placement,
    )


def _source_carton_supports_other(
    possible_support: MoveBatchCandidate,
    upper: MoveBatchCandidate,
) -> bool:
    if (
        possible_support.from_location_id is None
        or possible_support.from_location_id != upper.from_location_id
        or possible_support.source_placement is None
        or upper.source_placement is None
    ):
        return False
    lower_box = possible_support.source_placement
    upper_box = upper.source_placement
    return (
        lower_box.position_z_cm + lower_box.occupied_height_cm
        == upper_box.position_z_cm
        and _horizontal_footprints_overlap(lower_box, upper_box)
    )


def _target_carton_supports_other(
    possible_support: MoveBatchCandidate,
    upper: MoveBatchCandidate,
) -> bool:
    if (
        possible_support.to_location_id != upper.to_location_id
        or possible_support.target_placement is None
        or upper.target_placement is None
    ):
        return False
    lower_box = possible_support.target_placement
    upper_box = upper.target_placement
    return (
        lower_box.position_z_cm + lower_box.occupied_height_cm
        == upper_box.position_z_cm
        and _horizontal_footprints_overlap(lower_box, upper_box)
    )


def _horizontal_footprints_overlap(
    first: PlacedCarton,
    second: PlacedCarton,
) -> bool:
    return not (
        first.position_x_cm + first.occupied_width_cm
        <= second.position_x_cm
        or second.position_x_cm + second.occupied_width_cm
        <= first.position_x_cm
        or first.position_y_cm + first.occupied_depth_cm
        <= second.position_y_cm
        or second.position_y_cm + second.occupied_depth_cm
        <= first.position_y_cm
    )


def _find_cycle_components(
    dependencies: dict[int, set[int]],
) -> list[set[int]]:
    adjacency = {sequence: set() for sequence in dependencies}
    for dependent, predecessors in dependencies.items():
        for predecessor in predecessors:
            adjacency[predecessor].add(dependent)

    index = 0
    indexes: dict[int, int] = {}
    low_links: dict[int, int] = {}
    stack: list[int] = []
    on_stack: set[int] = set()
    cycle_components: list[set[int]] = []

    def visit(sequence: int) -> None:
        nonlocal index
        indexes[sequence] = index
        low_links[sequence] = index
        index += 1
        stack.append(sequence)
        on_stack.add(sequence)

        for neighbor in sorted(adjacency[sequence]):
            if neighbor not in indexes:
                visit(neighbor)
                low_links[sequence] = min(
                    low_links[sequence],
                    low_links[neighbor],
                )
            elif neighbor in on_stack:
                low_links[sequence] = min(
                    low_links[sequence],
                    indexes[neighbor],
                )

        if low_links[sequence] != indexes[sequence]:
            return
        component: list[int] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == sequence:
                break
        if len(component) > 1:
            cycle_components.append(set(component))

    for sequence in sorted(adjacency):
        if sequence not in indexes:
            visit(sequence)
    return sorted(
        cycle_components,
        key=lambda component: min(component),
    )


def _select_staging_move(
    component: set[int],
    eligible: dict[int, MoveBatchCandidate],
    seed: int,
) -> MoveBatchCandidate:
    """Prefer staging the highest source carton to preserve lower support."""
    return min(
        (eligible[sequence] for sequence in component),
        key=lambda move: (
            -(
                move.source_placement.position_z_cm
                if move.source_placement is not None
                else Decimal("0")
            ),
            _stable_tie_breaker(seed, "staging", move.move_sequence),
            move.move_sequence,
        ),
    )


def _fits_batch(
    selected: list[MoveBatchCandidate],
    candidate: MoveBatchCandidate,
    limits: MoveBatchLimits,
) -> bool:
    return (
        len(selected) + 1 <= limits.max_cartons
        and sum(
            (item.weight_kg for item in selected),
            start=candidate.weight_kg,
        )
        <= limits.max_weight_kg
        and sum(
            (item.volume_m3 for item in selected),
            start=candidate.volume_m3,
        )
        <= limits.max_volume_m3
    )


def _grouping_priority(
    move: MoveBatchCandidate,
    anchor: MoveBatchCandidate | None,
    seed: int,
) -> tuple[object, ...]:
    if anchor is None:
        return (
            move.from_location_key or (-1, -1, -1, -1),
            move.to_location_key,
            move.sku,
            _stable_tie_breaker(seed, "first", move.move_sequence),
            move.move_sequence,
        )
    return (
        0 if move.sku == anchor.sku else 1,
        0
        if (
            move.from_location_id == anchor.from_location_id
            and move.to_location_id == anchor.to_location_id
        )
        else 1,
        0 if move.from_location_id == anchor.from_location_id else 1,
        0 if move.to_location_id == anchor.to_location_id else 1,
        _location_distance(
            move.from_location_key,
            anchor.from_location_key,
        ),
        _location_distance(
            move.to_location_key,
            anchor.to_location_key,
        ),
        _stable_tie_breaker(seed, "group", move.move_sequence),
        move.move_sequence,
    )


def _location_distance(
    first: LocationSortKey | None,
    second: LocationSortKey | None,
) -> int:
    if first is None or second is None:
        return 1_000_000
    return sum(abs(left - right) for left, right in zip(first, second))


def _build_batch(
    sequence: int,
    items: list[MoveBatchCandidate],
    limits: MoveBatchLimits,
    cycle_sequences: set[int],
    dependencies: dict[int, set[int]],
    staged_items: list[MoveBatchCandidate] | None = None,
    finalized_items: list[MoveBatchCandidate] | None = None,
) -> PlannedMoveBatch:
    staged_items = staged_items or []
    finalized_items = finalized_items or []
    operational_items = items + finalized_items
    total_weight = sum(
        (item.weight_kg for item in operational_items),
        start=Decimal("0"),
    )
    total_volume = sum(
        (item.volume_m3 for item in operational_items),
        start=Decimal("0"),
    )
    utilization = max(
        total_weight / limits.max_weight_kg,
        total_volume / limits.max_volume_m3,
        Decimal(len(operational_items)) / Decimal(limits.max_cartons),
    )
    item_sequences = {item.move_sequence for item in items}
    reasons: list[str] = []
    if len({item.sku for item in items}) < len(items):
        reasons.append("same_sku_grouped")
    if len({item.from_location_id for item in items}) < len(items):
        reasons.append("shared_source_location")
    if len({item.to_location_id for item in items}) < len(items):
        reasons.append("shared_target_location")
    if any(dependencies[item.move_sequence] for item in items):
        reasons.append("movement_dependencies_ordered")
    requires_staging = bool(
        staged_items
        or finalized_items
        or item_sequences.intersection(cycle_sequences)
    )
    if staged_items:
        reasons.append("staging_pickup")
    if finalized_items:
        reasons.append("staging_finalized")
    if requires_staging:
        reasons.append("staging_buffer_required")
    if not reasons:
        reasons.append("nearby_movements_grouped")

    return PlannedMoveBatch(
        sequence=sequence,
        equipment_type=limits.equipment_type,
        items=tuple(items),
        total_weight_kg=total_weight,
        total_volume_m3=total_volume,
        capacity_utilization_percent=(utilization * PERCENT).quantize(
            PERCENT_QUANTUM
        ),
        stops=_build_stops(
            items,
            staged_items=staged_items,
            finalized_items=finalized_items,
        ),
        reasons=tuple(reasons),
        requires_staging_buffer=requires_staging,
        staged_items=tuple(staged_items),
        finalized_items=tuple(finalized_items),
    )


def _build_stops(
    items: list[MoveBatchCandidate],
    *,
    staged_items: list[MoveBatchCandidate],
    finalized_items: list[MoveBatchCandidate],
) -> tuple[PlannedBatchStop, ...]:
    staged_sequences = {
        item.move_sequence for item in staged_items
    }
    raw_stops: list[tuple[StopType, int, int]] = []
    for item in items:
        if item.from_location_id is not None:
            raw_stops.append(
                ("pickup", item.from_location_id, item.carton_id)
            )
    for item in items:
        if item.move_sequence not in staged_sequences:
            raw_stops.append(
                ("dropoff", item.to_location_id, item.carton_id)
            )
    for item in finalized_items:
        raw_stops.append(("dropoff", item.to_location_id, item.carton_id))

    grouped: list[tuple[StopType, int, list[int]]] = []
    for stop_type, location_id, carton_id in raw_stops:
        if (
            grouped
            and grouped[-1][0] == stop_type
            and grouped[-1][1] == location_id
        ):
            grouped[-1][2].append(carton_id)
        else:
            grouped.append((stop_type, location_id, [carton_id]))
    return tuple(
        PlannedBatchStop(
            sequence=index,
            type=stop_type,
            location_id=location_id,
            carton_ids=tuple(carton_ids),
        )
        for index, (stop_type, location_id, carton_ids) in enumerate(
            grouped,
            start=1,
        )
    )


def _validate_plan_completeness(
    eligible_sequences: set[int],
    batches: list[PlannedMoveBatch],
) -> None:
    batched_sequences = [
        sequence
        for batch in batches
        for sequence in batch.move_sequences
    ]
    if len(batched_sequences) != len(set(batched_sequences)):
        raise RuntimeError("A placed move was assigned to multiple batches")
    if set(batched_sequences) != eligible_sequences:
        raise RuntimeError("Not every eligible placed move was batched")


def _stable_tie_breaker(seed: int, *parts: object) -> str:
    value = ":".join(str(part) for part in (seed, *parts))
    return sha256(value.encode("utf-8")).hexdigest()
