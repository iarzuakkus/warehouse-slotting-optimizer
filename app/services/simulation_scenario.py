"""Simulation scenario orchestration without mutating real warehouse placement."""

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from itertools import combinations
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.algorithms.carton_placement import (
    CartonDimensions,
    ContainerDimensions,
    PlacedCarton,
)
from app.algorithms.slotting_optimizer import (
    SlottingCarton,
    SlottingConfig,
    SlottingLocation,
    SlottingMetrics,
    SlottingProposal,
    SlottingWeights,
    optimize_slotting,
)
from app.models.inventory import Carton, WarehouseRack
from app.models.optimization import OptimizationAssignment, OptimizationRun
from app.repositories.optimization_run import OptimizationRunRepository
from app.repositories.warehouse_rack import WarehouseRackRepository
from app.schemas.optimization_run import OptimizationRunStatus
from app.schemas.simulation_scenario import (
    SimulationMetricSet,
    SimulationMoveListRead,
    SimulationMoveRead,
    SimulationPathPointRead,
    SimulationScenarioCreate,
    SimulationScenarioParameters,
    SimulationScenarioRead,
    SimulationScenarioResultRead,
    SimulationScenarioUpdate,
)
from app.schemas.warehouse_rack import WarehouseRackSceneRead
from app.services.abc_analysis import ABCAnalysisService
from app.services.fp_growth_analysis import FPGrowthAnalysisService
from app.services.warehouse_graph import (
    WarehouseGraphDataError,
    WarehouseGraphLocationNotFoundError,
    WarehouseGraphService,
    WarehouseGraphSnapshot,
)
from app.services.warehouse_rack import WarehouseRackService


class SimulationScenarioNotFoundError(Exception):
    """Raised when a simulation scenario does not exist."""


class SimulationScenarioConflictError(Exception):
    """Raised when scenario state prevents the requested operation."""


class SimulationScenarioExecutionError(Exception):
    """Raised after a failed scenario execution has been persisted."""


class SimulationScenarioService:
    walking_speed_m_per_second = Decimal("1.40")
    handling_seconds_per_move = Decimal("8.00")
    duration_quantum = Decimal("0.01")
    metric_quantum = Decimal("0.01")

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = OptimizationRunRepository(session)
        self.rack_repository = WarehouseRackRepository(session)
        self.abc_service = ABCAnalysisService(session)
        self.fp_growth_service = FPGrowthAnalysisService(session)
        self.graph_service = WarehouseGraphService(session)
        self.rack_service = WarehouseRackService(session)

    def list_scenarios(
        self,
        offset: int = 0,
        limit: int = 100,
        scenario_status: OptimizationRunStatus | None = None,
    ) -> list[SimulationScenarioRead]:
        scenarios = self.repository.list_scenarios(
            offset=offset,
            limit=limit,
            scenario_status=scenario_status,
        )
        return [self._build_scenario_read(scenario) for scenario in scenarios]

    def get_scenario(self, scenario_id: int) -> SimulationScenarioRead:
        return self._build_scenario_read(self._get_scenario(scenario_id))

    def create_scenario(
        self,
        data: SimulationScenarioCreate,
    ) -> SimulationScenarioRead:
        try:
            scenario = self.repository.create_scenario(data)
            self.session.commit()
            self.session.refresh(scenario)
            return self._build_scenario_read(scenario)
        except IntegrityError as exc:
            self.session.rollback()
            raise SimulationScenarioConflictError(
                "Simulation scenario violates a database rule"
            ) from exc

    def update_scenario(
        self,
        scenario_id: int,
        data: SimulationScenarioUpdate,
    ) -> SimulationScenarioRead:
        scenario = self._get_scenario(scenario_id, for_update=True)
        if scenario.status != "pending":
            self.session.rollback()
            raise SimulationScenarioConflictError(
                "Only pending simulation scenarios can be edited"
            )
        try:
            self.repository.update_scenario(scenario, data)
            self.session.commit()
            return self.get_scenario(scenario_id)
        except IntegrityError as exc:
            self.session.rollback()
            raise SimulationScenarioConflictError(
                "Simulation scenario update violates a database rule"
            ) from exc

    def delete_scenario(self, scenario_id: int) -> None:
        scenario = self._get_scenario(scenario_id, for_update=True)
        if scenario.status == "running":
            self.session.rollback()
            raise SimulationScenarioConflictError(
                "A running simulation scenario cannot be deleted"
            )
        self.repository.delete_scenario(scenario)
        self.session.commit()

    def run_scenario(self, scenario_id: int) -> SimulationScenarioRead:
        scenario = self._get_scenario(scenario_id, for_update=True)
        if scenario.status != "pending":
            self.session.rollback()
            raise SimulationScenarioConflictError(
                "Only pending simulation scenarios can be run"
            )

        try:
            scenario.status = "running"
            scenario.progress_percent = Decimal("5")
            scenario.started_at = datetime.now(timezone.utc)
            scenario.completed_at = None
            scenario.error_message = None
            self.repository.save(scenario)

            parameters = SimulationScenarioParameters.model_validate(
                scenario.parameters
            )
            racks = self.rack_repository.list_racks_for_simulation(
                aisle_filter=parameters.aisle_filter,
                level_filter=parameters.level_filter,
            )
            if not racks or not any(rack.locations for rack in racks):
                raise SimulationScenarioConflictError(
                    "No warehouse locations match the scenario scope"
                )

            config = self._build_config(scenario, parameters)
            abc_classes = self._load_abc_classes(racks)
            co_shipped_skus = self._load_co_shipped_skus(racks)
            locations, cartons = self._build_optimizer_input(
                racks,
                abc_classes,
                co_shipped_skus,
            )
            current_metrics = self._calculate_current_metrics(
                racks,
                config.weights,
            )
            scenario.source_snapshot = self._build_source_snapshot(racks)
            scenario.progress_percent = Decimal("35")

            result = optimize_slotting(locations, cartons, config)
            graph, graph_coordinates = self._load_graph_context()
            assignments = self._build_assignments(
                result.moves,
                locations,
                graph,
                graph_coordinates,
            )
            self.repository.replace_assignments(scenario, assignments)

            result_read = self._build_result_read(
                current_metrics,
                result.metrics,
                assignments,
                config.weights,
            )
            scenario.result_metrics = result_read.model_dump(mode="json")
            scenario.objective_value = result_read.proposed.objective_score
            scenario.progress_percent = Decimal("100")
            scenario.status = "completed"
            scenario.completed_at = datetime.now(timezone.utc)
            self.repository.save(scenario)
            self.session.commit()
            return self.get_scenario(scenario_id)
        except SimulationScenarioConflictError:
            self.session.rollback()
            raise
        except Exception as exc:
            self.session.rollback()
            self._record_failed_run(scenario_id, exc)
            raise SimulationScenarioExecutionError(
                f"Simulation scenario {scenario_id} failed"
            ) from exc

    def get_moves(self, scenario_id: int) -> SimulationMoveListRead:
        scenario = self._get_completed_scenario(scenario_id)
        assignments = sorted(
            scenario.assignments,
            key=lambda item: (item.sequence_number or 0, item.id),
        )
        moves = [self._build_move_read(assignment) for assignment in assignments]
        return SimulationMoveListRead(
            scenario_id=scenario.id,
            move_count=sum(move.result_status == "placed" for move in moves),
            unplaced_count=sum(
                move.result_status == "unplaced" for move in moves
            ),
            moves=moves,
        )

    def get_move(
        self,
        scenario_id: int,
        sequence: int,
    ) -> SimulationMoveRead:
        moves = self.get_moves(scenario_id).moves
        for move in moves:
            if move.sequence == sequence:
                return move
        raise SimulationScenarioNotFoundError(
            f"Move {sequence} not found in simulation scenario {scenario_id}"
        )

    def get_scene(
        self,
        scenario_id: int,
        step: int | None = None,
    ) -> list[WarehouseRackSceneRead]:
        scenario = self._get_completed_scenario(scenario_id)
        assignments = sorted(
            scenario.assignments,
            key=lambda item: (item.sequence_number or 0, item.id),
        )
        effective_step = len(assignments) if step is None else step
        if effective_step < 0 or effective_step > len(assignments):
            raise SimulationScenarioConflictError(
                f"step must be between 0 and {len(assignments)}"
            )
        if scenario.source_snapshot is None:
            raise SimulationScenarioConflictError(
                "Simulation scenario does not contain a source snapshot"
            )

        snapshot = deepcopy(scenario.source_snapshot)
        racks = snapshot.get("racks", [])
        metadata = snapshot.get("carton_metadata", {})
        self._apply_assignments_to_scene(
            racks,
            assignments[:effective_step],
        )
        self._refresh_scene_utilization(racks, metadata)
        return [WarehouseRackSceneRead.model_validate(rack) for rack in racks]

    def _get_scenario(
        self,
        scenario_id: int,
        *,
        for_update: bool = False,
    ) -> OptimizationRun:
        scenario = self.repository.get_scenario_by_id(
            scenario_id,
            for_update=for_update,
        )
        if scenario is None:
            if for_update:
                self.session.rollback()
            raise SimulationScenarioNotFoundError(
                f"Simulation scenario {scenario_id} not found"
            )
        return scenario

    def _get_completed_scenario(self, scenario_id: int) -> OptimizationRun:
        scenario = self._get_scenario(scenario_id)
        if scenario.status != "completed":
            raise SimulationScenarioConflictError(
                "Simulation results are available only after completion"
            )
        return scenario

    @staticmethod
    def _build_config(
        scenario: OptimizationRun,
        parameters: SimulationScenarioParameters,
    ) -> SlottingConfig:
        weights = parameters.objective_weights
        return SlottingConfig(
            seed=scenario.seed or 0,
            group_same_sku=parameters.group_same_sku,
            prefer_lower_levels_for_heavy_cartons=(
                parameters.prefer_lower_levels_for_heavy_cartons
            ),
            minimize_dispatch_distance=parameters.minimize_dispatch_distance,
            minimize_moves=parameters.minimize_moves,
            improve_volume_utilization=parameters.improve_volume_utilization,
            weights=SlottingWeights(**weights.model_dump()),
        )

    def _load_abc_classes(
        self,
        racks: list[WarehouseRack],
    ) -> dict[str, str]:
        synthetic_only = all(rack.aisle.startswith("SYN-") for rack in racks)
        return {
            result.sku: result.abc_class
            for result in self.abc_service.run_analysis(
                synthetic_only=synthetic_only
            )
        }

    def _load_co_shipped_skus(
        self,
        racks: list[WarehouseRack],
    ) -> dict[str, frozenset[str]]:
        synthetic_only = all(rack.aisle.startswith("SYN-") for rack in racks)
        analysis = self.fp_growth_service.run_analysis(
            synthetic_only=synthetic_only
        )
        related: dict[str, set[str]] = {}
        for rule in analysis.rules:
            items = sorted(set(rule.antecedent) | set(rule.consequent))
            for first, second in combinations(items, 2):
                related.setdefault(first, set()).add(second)
                related.setdefault(second, set()).add(first)
        return {sku: frozenset(values) for sku, values in related.items()}

    def _build_optimizer_input(
        self,
        racks: list[WarehouseRack],
        abc_classes: dict[str, str],
        co_shipped_skus: dict[str, frozenset[str]],
    ) -> tuple[list[SlottingLocation], list[SlottingCarton]]:
        aisle_ranks = {
            aisle: index
            for index, aisle in enumerate(
                sorted({rack.aisle for rack in racks}),
                start=1,
            )
        }
        level_ranks = {
            level: index
            for index, level in enumerate(
                sorted(
                    {
                        location.level
                        for rack in racks
                        for location in rack.locations
                    }
                ),
                start=1,
            )
        }
        locations: list[SlottingLocation] = []
        movable_cartons: list[SlottingCarton] = []

        for rack in sorted(racks, key=lambda item: (item.aisle, item.bay)):
            for location in sorted(
                rack.locations,
                key=lambda item: (item.level, item.slot, item.id),
            ):
                fixed = [
                    carton
                    for carton in location.current_cartons
                    if carton.status in {"depleted", "quarantined"}
                ]
                fixed_weight = self._sum_carton_weights(fixed)
                fixed_placements = tuple(
                    self._to_placed_carton(carton)
                    for carton in fixed
                    if self._has_complete_placement(carton)
                )
                locations.append(
                    SlottingLocation(
                        id=location.id,
                        aisle=location.aisle,
                        bay=location.bay,
                        level=location.level,
                        slot=location.slot,
                        aisle_rank=aisle_ranks[location.aisle],
                        level_rank=level_ranks[location.level],
                        is_active=rack.is_active and location.is_active,
                        dimensions=ContainerDimensions(
                            width_cm=location.usable_width_cm,
                            depth_cm=location.usable_depth_cm,
                            height_cm=location.usable_height_cm,
                        ),
                        max_weight_kg=location.max_weight_kg,
                        dispatch_distance_m=location.distance_from_dispatch_m,
                        fixed_cartons=fixed_placements,
                        fixed_weight_kg=fixed_weight,
                        fixed_skus=frozenset(
                            carton.product_packaging.product.sku
                            for carton in fixed
                        ),
                    )
                )
                for carton in location.current_cartons:
                    if carton.status in {"depleted", "quarantined"}:
                        continue
                    movable_cartons.append(
                        self._to_slotting_carton(
                            carton,
                            abc_classes,
                            co_shipped_skus,
                        )
                    )
        return locations, movable_cartons

    @staticmethod
    def _to_slotting_carton(
        carton: Carton,
        abc_classes: dict[str, str],
        co_shipped_skus: dict[str, frozenset[str]],
    ) -> SlottingCarton:
        packaging = carton.product_packaging
        product = packaging.product
        carton_type = packaging.carton_type
        weight = (
            product.unit_weight_kg * carton.current_qty
            if product.unit_weight_kg is not None
            else None
        )
        return SlottingCarton(
            id=carton.id,
            carton_number=carton.carton_number,
            product_id=product.id,
            sku=product.sku,
            dimensions=CartonDimensions(
                length_cm=carton_type.outer_length_cm,
                width_cm=carton_type.outer_width_cm,
                height_cm=carton_type.outer_height_cm,
            ),
            weight_kg=weight,
            current_location_id=carton.current_location_id,
            current_position_x_cm=carton.position_x_cm,
            current_position_y_cm=carton.position_y_cm,
            current_position_z_cm=carton.position_z_cm,
            current_rotation_degrees=carton.rotation_degrees,
            abc_class=abc_classes.get(product.sku),
            co_shipped_skus=co_shipped_skus.get(product.sku, frozenset()),
        )

    @staticmethod
    def _to_placed_carton(carton: Carton) -> PlacedCarton:
        carton_type = carton.product_packaging.carton_type
        rotated = carton.rotation_degrees == 90
        return PlacedCarton(
            carton_id=carton.id,
            position_x_cm=carton.position_x_cm,
            position_y_cm=carton.position_y_cm,
            position_z_cm=carton.position_z_cm,
            occupied_width_cm=(
                carton_type.outer_width_cm
                if rotated
                else carton_type.outer_length_cm
            ),
            occupied_depth_cm=(
                carton_type.outer_length_cm
                if rotated
                else carton_type.outer_width_cm
            ),
            occupied_height_cm=carton_type.outer_height_cm,
            rotation_degrees=carton.rotation_degrees,
        )

    def _build_source_snapshot(
        self,
        racks: list[WarehouseRack],
    ) -> dict[str, Any]:
        metadata: dict[str, dict[str, str | None]] = {}
        for rack in racks:
            for location in rack.locations:
                for carton in location.current_cartons:
                    weight = self._carton_weight(carton)
                    metadata[str(carton.id)] = {
                        "weight_kg": str(weight) if weight is not None else None,
                    }
        return {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "racks": [
                self.rack_service._build_scene_rack(rack).model_dump(mode="json")
                for rack in racks
            ],
            "carton_metadata": metadata,
        }

    def _calculate_current_metrics(
        self,
        racks: list[WarehouseRack],
        weights: SlottingWeights,
    ) -> SlottingMetrics:
        active_locations = [
            location
            for rack in racks
            if rack.is_active
            for location in rack.locations
            if location.is_active
        ]
        cartons_by_location = {
            location.id: [
                carton
                for carton in location.current_cartons
                if self._has_complete_placement(carton)
            ]
            for location in active_locations
        }
        placed_count = sum(len(cartons) for cartons in cartons_by_location.values())
        total_distance = sum(
            (
                location.distance_from_dispatch_m
                * len(cartons_by_location[location.id])
                for location in active_locations
            ),
            start=Decimal("0"),
        )
        average_distance = (
            total_distance / placed_count if placed_count else Decimal("0")
        )
        location_weights = [
            self._sum_carton_weights(cartons_by_location[location.id])
            for location in active_locations
        ]
        weight_utilization: Decimal | None = None
        known_capacities = all(
            location.max_weight_kg is not None
            for location in active_locations
        )
        known_weights = all(
            value is not None for value in location_weights
        )
        if known_capacities and known_weights:
            total_capacity = sum(
                (
                    location.max_weight_kg or Decimal("0")
                    for location in active_locations
                ),
                start=Decimal("0"),
            )
            used_weight = sum(
                (value or Decimal("0") for value in location_weights),
                start=Decimal("0"),
            )
            if total_capacity > 0:
                weight_utilization = (
                    used_weight / total_capacity * Decimal("100")
                ).quantize(self.metric_quantum)

        used_volume = sum(
            (
                self._carton_volume(carton)
                for cartons in cartons_by_location.values()
                for carton in cartons
            ),
            start=Decimal("0"),
        )
        total_volume = sum(
            (
                location.usable_width_cm
                * location.usable_depth_cm
                * location.usable_height_cm
                for location in active_locations
            ),
            start=Decimal("0"),
        )
        sku_locations: dict[str, set[int]] = {}
        for location in active_locations:
            for carton in cartons_by_location[location.id]:
                sku = carton.product_packaging.product.sku
                sku_locations.setdefault(sku, set()).add(location.id)

        metrics = SlottingMetrics(
            total_dispatch_distance=total_distance.quantize(self.metric_quantum),
            average_dispatch_distance=average_distance.quantize(
                self.metric_quantum
            ),
            weight_utilization_percent=weight_utilization,
            volume_utilization_percent=(
                (used_volume / total_volume * Decimal("100")).quantize(
                    self.metric_quantum
                )
                if total_volume > 0
                else Decimal("0")
            ),
            used_location_count=sum(
                bool(cartons) for cartons in cartons_by_location.values()
            ),
            split_sku_count=sum(
                len(location_ids) > 1
                for location_ids in sku_locations.values()
            ),
            moved_carton_count=0,
            unplaced_carton_count=0,
            objective_score=Decimal("0"),
        )
        return self._replace_objective_score(metrics, weights)

    def _build_assignments(
        self,
        proposals: tuple[SlottingProposal, ...],
        locations: list[SlottingLocation],
        graph: WarehouseGraphSnapshot | None,
        graph_coordinates: dict[str, tuple[Decimal, Decimal]],
    ) -> list[OptimizationAssignment]:
        locations_by_id = {location.id: location for location in locations}
        assignments: list[OptimizationAssignment] = []
        for sequence, proposal in enumerate(proposals, start=1):
            distance, path = self._movement_details(
                proposal,
                locations_by_id,
                graph,
                graph_coordinates,
            )
            duration = (
                self.handling_seconds_per_move
                + distance / self.walking_speed_m_per_second
                if proposal.result_status == "placed"
                else Decimal("0")
            ).quantize(self.duration_quantum)
            assignments.append(
                OptimizationAssignment(
                    carton_id=proposal.carton_id,
                    sequence_number=sequence,
                    result_status=proposal.result_status,
                    from_location_id=proposal.from_location_id,
                    to_location_id=proposal.to_location_id,
                    from_position_x_cm=proposal.from_position_x_cm,
                    from_position_y_cm=proposal.from_position_y_cm,
                    from_position_z_cm=proposal.from_position_z_cm,
                    from_rotation_degrees=proposal.from_rotation_degrees,
                    proposed_position_x_cm=proposal.proposed_position_x_cm,
                    proposed_position_y_cm=proposal.proposed_position_y_cm,
                    proposed_position_z_cm=proposal.proposed_position_z_cm,
                    proposed_rotation_degrees=proposal.proposed_rotation_degrees,
                    assignment_score=proposal.score,
                    estimated_duration_seconds=duration,
                    travel_distance_m=distance,
                    movement_path=path,
                    reasons=list(proposal.reasons),
                    unplaced_reason=proposal.unplaced_reason,
                )
            )
        return assignments

    def _movement_details(
        self,
        proposal: SlottingProposal,
        locations_by_id: dict[int, SlottingLocation],
        graph: WarehouseGraphSnapshot | None,
        coordinates: dict[str, tuple[Decimal, Decimal]],
    ) -> tuple[Decimal, list[dict[str, Any]]]:
        if proposal.to_location_id is None:
            return Decimal("0"), []
        path_nodes: tuple[str, ...] = ()
        distance: Decimal
        try:
            if graph is None:
                raise WarehouseGraphLocationNotFoundError
            if proposal.from_location_id is None:
                shortest = graph.path_from_dispatch(proposal.to_location_id)
            else:
                shortest = graph.path_between_locations(
                    proposal.from_location_id,
                    proposal.to_location_id,
                )
            distance = Decimal(str(shortest.distance_m))
            path_nodes = shortest.nodes
        except (WarehouseGraphLocationNotFoundError, ValueError):
            target = locations_by_id[proposal.to_location_id]
            source = locations_by_id.get(proposal.from_location_id)
            distance = (
                abs(
                    target.dispatch_distance_m
                    - source.dispatch_distance_m
                )
                if source is not None
                else target.dispatch_distance_m
            )

        path = []
        for index, node_id in enumerate(path_nodes):
            point = coordinates.get(node_id)
            if point is None:
                continue
            path.append(
                {
                    "sequence": index,
                    "node_id": node_id,
                    "x": str(point[0]),
                    "y": str(point[1]),
                }
            )
        return distance.quantize(self.metric_quantum), path

    def _load_graph_context(
        self,
    ) -> tuple[
        WarehouseGraphSnapshot | None,
        dict[str, tuple[Decimal, Decimal]],
    ]:
        try:
            snapshot = self.graph_service.load_snapshot()
            layout = snapshot.build_layout(include_locations=True)
            coordinates = {
                node.id: (Decimal(str(node.x)), Decimal(str(node.y)))
                for node in layout.nodes
            }
            return snapshot, coordinates
        except WarehouseGraphDataError:
            return None, {}

    def _build_result_read(
        self,
        current: SlottingMetrics,
        proposed: SlottingMetrics,
        assignments: list[OptimizationAssignment],
        weights: SlottingWeights,
    ) -> SimulationScenarioResultRead:
        proposed = self._replace_objective_score(proposed, weights)
        current_read = self._metric_read(current)
        proposed_read = self._metric_read(proposed)
        improvement = self._improvement_percent(
            current_read.objective_score,
            proposed_read.objective_score,
        )
        return SimulationScenarioResultRead(
            current=current_read,
            proposed=proposed_read,
            objective_improvement_percent=improvement,
            estimated_duration_seconds=sum(
                (
                    assignment.estimated_duration_seconds or Decimal("0")
                    for assignment in assignments
                ),
                start=Decimal("0"),
            ),
            total_movement_distance_m=sum(
                (
                    assignment.travel_distance_m or Decimal("0")
                    for assignment in assignments
                ),
                start=Decimal("0"),
            ),
        )

    @staticmethod
    def _replace_objective_score(
        metrics: SlottingMetrics,
        weights: SlottingWeights,
    ) -> SlottingMetrics:
        score = (
            metrics.total_dispatch_distance * weights.dispatch_distance
            + Decimal(metrics.used_location_count)
            * weights.location_consolidation
            + Decimal(metrics.split_sku_count) * weights.split_sku
            + Decimal(metrics.moved_carton_count) * weights.moves
            - metrics.volume_utilization_percent
            * weights.volume_utilization
        )
        return SlottingMetrics(
            **{
                **metrics.__dict__,
                "objective_score": score.quantize(Decimal("0.000001")),
            }
        )

    @staticmethod
    def _metric_read(metrics: SlottingMetrics) -> SimulationMetricSet:
        return SimulationMetricSet(**metrics.__dict__)

    def _improvement_percent(
        self,
        current: Decimal,
        proposed: Decimal,
    ) -> Decimal | None:
        if current == 0:
            return None
        return ((current - proposed) / abs(current) * Decimal("100")).quantize(
            self.metric_quantum
        )

    def _build_scenario_read(
        self,
        scenario: OptimizationRun,
    ) -> SimulationScenarioRead:
        return SimulationScenarioRead(
            id=scenario.id,
            name=scenario.name or f"Scenario {scenario.id}",
            seed=scenario.seed or 0,
            algorithm_name=scenario.algorithm_name,
            status=scenario.status,
            progress_percent=scenario.progress_percent,
            parameters=SimulationScenarioParameters.model_validate(
                scenario.parameters
            ),
            result=(
                SimulationScenarioResultRead.model_validate(
                    scenario.result_metrics
                )
                if scenario.result_metrics is not None
                else None
            ),
            started_at=scenario.started_at,
            completed_at=scenario.completed_at,
            error_message=scenario.error_message,
            created_at=scenario.created_at,
            updated_at=scenario.updated_at,
        )

    @staticmethod
    def _build_move_read(
        assignment: OptimizationAssignment,
    ) -> SimulationMoveRead:
        carton = assignment.carton
        product = carton.product_packaging.product
        return SimulationMoveRead(
            id=assignment.id,
            sequence=assignment.sequence_number,
            result_status=assignment.result_status,
            carton_id=carton.id,
            carton_number=carton.carton_number,
            product_id=product.id,
            sku=product.sku,
            from_location_id=assignment.from_location_id,
            to_location_id=assignment.to_location_id,
            from_position_x_cm=assignment.from_position_x_cm,
            from_position_y_cm=assignment.from_position_y_cm,
            from_position_z_cm=assignment.from_position_z_cm,
            from_rotation_degrees=assignment.from_rotation_degrees,
            proposed_position_x_cm=assignment.proposed_position_x_cm,
            proposed_position_y_cm=assignment.proposed_position_y_cm,
            proposed_position_z_cm=assignment.proposed_position_z_cm,
            proposed_rotation_degrees=assignment.proposed_rotation_degrees,
            assignment_score=assignment.assignment_score,
            estimated_duration_seconds=(
                assignment.estimated_duration_seconds
            ),
            travel_distance_m=assignment.travel_distance_m,
            path=[
                SimulationPathPointRead.model_validate(point)
                for point in assignment.movement_path
            ],
            reasons=assignment.reasons,
            unplaced_reason=assignment.unplaced_reason,
        )

    @staticmethod
    def _apply_assignments_to_scene(
        racks: list[dict[str, Any]],
        assignments: list[OptimizationAssignment],
    ) -> None:
        locations: dict[int, dict[str, Any]] = {}
        cartons: dict[int, dict[str, Any]] = {}
        for rack in racks:
            for location in rack["locations"]:
                locations[int(location["id"])] = location
                for carton in location["cartons"]:
                    cartons[int(carton["id"])] = carton

        for assignment in assignments:
            carton = cartons.get(assignment.carton_id)
            for location in locations.values():
                location["cartons"] = [
                    item
                    for item in location["cartons"]
                    if int(item["id"]) != assignment.carton_id
                ]
            if (
                assignment.result_status == "unplaced"
                or assignment.to_location_id is None
                or carton is None
            ):
                continue
            carton.update(
                {
                    "position_x_cm": str(assignment.proposed_position_x_cm),
                    "position_y_cm": str(assignment.proposed_position_y_cm),
                    "position_z_cm": str(assignment.proposed_position_z_cm),
                    "rotation_degrees": assignment.proposed_rotation_degrees,
                }
            )
            locations[assignment.to_location_id]["cartons"].append(carton)

    def _refresh_scene_utilization(
        self,
        racks: list[dict[str, Any]],
        metadata: dict[str, dict[str, str | None]],
    ) -> None:
        for rack in racks:
            for location in rack["locations"]:
                carton_weights = [
                    metadata.get(str(carton["id"]), {}).get("weight_kg")
                    for carton in location["cartons"]
                ]
                used_weight = (
                    sum(
                        (
                            Decimal(value)
                            for value in carton_weights
                            if value is not None
                        ),
                        start=Decimal("0"),
                    )
                    if all(value is not None for value in carton_weights)
                    else None
                )
                max_weight = (
                    Decimal(location["max_weight_kg"])
                    if location["max_weight_kg"] is not None
                    else None
                )
                location["used_weight_kg"] = (
                    str(used_weight) if used_weight is not None else None
                )
                location["weight_utilization_percent"] = (
                    str(
                        (
                            used_weight / max_weight * Decimal("100")
                        ).quantize(self.metric_quantum)
                    )
                    if used_weight is not None and max_weight is not None
                    else None
                )
                used_volume = sum(
                    (
                        Decimal(carton["outer_length_cm"])
                        * Decimal(carton["outer_width_cm"])
                        * Decimal(carton["outer_height_cm"])
                        for carton in location["cartons"]
                    ),
                    start=Decimal("0"),
                )
                usable_volume = (
                    Decimal(location["usable_width_cm"])
                    * Decimal(location["usable_depth_cm"])
                    * Decimal(location["usable_height_cm"])
                )
                location["volume_utilization_percent"] = str(
                    (used_volume / usable_volume * Decimal("100")).quantize(
                        self.metric_quantum
                    )
                )
                location["cartons"].sort(
                    key=lambda carton: (carton["carton_number"], carton["id"])
                )

    def _record_failed_run(self, scenario_id: int, error: Exception) -> None:
        scenario = self.repository.get_scenario_by_id(scenario_id)
        if scenario is None:
            return
        scenario.status = "failed"
        scenario.progress_percent = Decimal("0")
        scenario.completed_at = datetime.now(timezone.utc)
        scenario.error_message = str(error)[:1000] or error.__class__.__name__
        self.repository.save(scenario)
        self.session.commit()

    @staticmethod
    def _has_complete_placement(carton: Carton) -> bool:
        return (
            carton.position_x_cm is not None
            and carton.position_y_cm is not None
            and carton.position_z_cm is not None
            and carton.rotation_degrees is not None
        )

    @staticmethod
    def _carton_weight(carton: Carton) -> Decimal | None:
        unit_weight = carton.product_packaging.product.unit_weight_kg
        return (
            unit_weight * carton.current_qty
            if unit_weight is not None
            else None
        )

    @classmethod
    def _sum_carton_weights(
        cls,
        cartons: list[Carton],
    ) -> Decimal | None:
        weights = [cls._carton_weight(carton) for carton in cartons]
        if any(weight is None for weight in weights):
            return None
        return sum(
            (weight for weight in weights if weight is not None),
            start=Decimal("0"),
        )

    @staticmethod
    def _carton_volume(carton: Carton) -> Decimal:
        carton_type = carton.product_packaging.carton_type
        return (
            carton_type.outer_length_cm
            * carton_type.outer_width_cm
            * carton_type.outer_height_cm
        )
