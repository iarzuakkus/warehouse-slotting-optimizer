"""Read-only operational batching for completed simulation movements."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.algorithms.carton_placement import (
    CartonDimensions,
    PlacedCarton,
    build_placed_carton,
)
from app.algorithms.move_batching import (
    MoveBatchCandidate,
    MoveBatchLimits,
    MoveBatchPlan,
    PlannedMoveBatch,
    plan_move_batches,
)
from app.models.inventory import WarehouseLocation
from app.models.optimization import OptimizationAssignment, OptimizationRun
from app.repositories.optimization_run import OptimizationRunRepository
from app.schemas.simulation_scenario import (
    SimulationMoveBatchItemRead,
    SimulationMoveBatchListRead,
    SimulationMoveBatchRead,
    SimulationMoveBatchStopRead,
    SimulationMoveBatchValidationRead,
    SimulationScenarioParameters,
)
from app.schemas.warehouse_rack import WarehouseRackSceneRead
from app.services.simulation_scenario import (
    SimulationScenarioConflictError,
    SimulationScenarioNotFoundError,
    SimulationScenarioService,
)
from app.services.warehouse_graph import (
    WarehouseGraphDataError,
    WarehouseGraphLocationNotFoundError,
    WarehouseGraphService,
    WarehouseGraphSnapshot,
)


class SimulationMoveBatchNotFoundError(Exception):
    """Raised when a batch sequence does not exist in a scenario plan."""


class SimulationMoveBatchService:
    cubic_centimeters_per_cubic_meter = Decimal("1000000")
    walking_speed_m_per_second = Decimal("1.40")
    handling_seconds_per_carton = Decimal("8.00")
    weight_quantum = Decimal("0.001")
    volume_quantum = Decimal("0.000001")
    distance_quantum = Decimal("0.01")
    duration_quantum = Decimal("0.01")
    percent_quantum = Decimal("0.01")

    def __init__(self, session: Session) -> None:
        self.repository = OptimizationRunRepository(session)
        self.graph_service = WarehouseGraphService(session)
        self.scenario_service = SimulationScenarioService(session)

    def get_move_batches(
        self,
        scenario_id: int,
    ) -> SimulationMoveBatchListRead:
        scenario = self._get_completed_scenario(scenario_id)
        parameters, candidates, plan = self._build_plan(
            scenario,
        )
        graph = self._load_graph()
        locations = self._locations_by_id(scenario)
        batch_reads = [
            self._build_batch_read(batch, graph, locations)
            for batch in plan.batches
        ]
        operational_distance = sum(
            (batch.estimated_distance_m for batch in batch_reads),
            start=Decimal("0"),
        )
        individual_distance = sum(
            (candidate.individual_distance_m for candidate in candidates),
            start=Decimal("0"),
        )
        estimated_duration = sum(
            (
                batch.estimated_duration_seconds
                for batch in batch_reads
            ),
            start=Decimal("0"),
        )
        capacity_utilization = (
            sum(
                (
                    batch.capacity_utilization_percent
                    for batch in batch_reads
                ),
                start=Decimal("0"),
            )
            / len(batch_reads)
            if batch_reads
            else Decimal("0")
        )
        return SimulationMoveBatchListRead(
            scenario_id=scenario.id,
            equipment_type=parameters.equipment_type,
            batch_count=len(batch_reads),
            carton_move_count=(
                sum(batch.carton_count for batch in batch_reads)
                + len(plan.unbatched_items)
            ),
            operational_distance_m=operational_distance.quantize(
                self.distance_quantum
            ),
            individual_distance_m=individual_distance.quantize(
                self.distance_quantum
            ),
            estimated_duration_seconds=estimated_duration.quantize(
                self.duration_quantum
            ),
            capacity_utilization_percent=capacity_utilization.quantize(
                self.percent_quantum
            ),
            requires_staging_buffer=plan.requires_staging_buffer,
            staging_move_sequences=list(plan.staging_move_sequences),
            batches=batch_reads,
            unbatched_items=[
                self._build_item_read(item)
                for item in plan.unbatched_items
            ],
            validation_errors=[
                SimulationMoveBatchValidationRead(
                    move_sequence=error.move_sequence,
                    carton_id=error.carton_id,
                    code=error.code,
                    message=error.message,
                )
                for error in plan.validation_errors
            ],
        )

    def get_move_batch(
        self,
        scenario_id: int,
        sequence: int,
    ) -> SimulationMoveBatchRead:
        plan = self.get_move_batches(scenario_id)
        for batch in plan.batches:
            if batch.sequence == sequence:
                return batch
        raise SimulationMoveBatchNotFoundError(
            f"Move batch {sequence} not found in simulation scenario "
            f"{scenario_id}"
        )

    def get_batch_scene(
        self,
        scenario_id: int,
        batch_step: int,
    ) -> list[WarehouseRackSceneRead]:
        scenario = self._get_completed_scenario(scenario_id)
        _, _, plan = self._build_plan(scenario)
        if batch_step < 0 or batch_step > len(plan.batches):
            raise SimulationScenarioConflictError(
                f"step must be between 0 and {len(plan.batches)}"
            )
        move_sequence_batches = [
            list(batch.move_sequences)
            for batch in plan.batches[:batch_step]
        ]
        staged_sequence_batches = [
            list(batch.staged_move_sequences)
            for batch in plan.batches[:batch_step]
        ]
        finalized_sequence_batches = [
            list(batch.finalized_move_sequences)
            for batch in plan.batches[:batch_step]
        ]
        return self.scenario_service.get_scene_for_move_sequence_batches(
            scenario_id,
            move_sequence_batches,
            staged_sequence_batches,
            finalized_sequence_batches,
        )

    def _build_plan(
        self,
        scenario: OptimizationRun,
    ) -> tuple[
        SimulationScenarioParameters,
        list[MoveBatchCandidate],
        MoveBatchPlan,
    ]:
        parameters = SimulationScenarioParameters.model_validate(
            scenario.parameters
        )
        candidates = self._build_candidates(scenario)
        limits = MoveBatchLimits(
            equipment_type=parameters.equipment_type,
            max_weight_kg=parameters.max_batch_weight_kg,
            max_volume_m3=parameters.max_batch_volume_m3,
            max_cartons=parameters.max_cartons_per_batch,
        )
        plan = plan_move_batches(
            candidates,
            limits,
            seed=scenario.seed or 0,
        )
        return parameters, candidates, plan

    def _get_completed_scenario(self, scenario_id: int) -> OptimizationRun:
        scenario = self.repository.get_scenario_by_id(scenario_id)
        if scenario is None:
            raise SimulationScenarioNotFoundError(
                f"Simulation scenario {scenario_id} not found"
            )
        if scenario.status != "completed":
            raise SimulationScenarioConflictError(
                "Move batches are available only after completion"
            )
        return scenario

    def _build_candidates(
        self,
        scenario: OptimizationRun,
    ) -> list[MoveBatchCandidate]:
        assignments = sorted(
            (
                assignment
                for assignment in scenario.assignments
                if assignment.result_status == "placed"
            ),
            key=lambda assignment: (
                assignment.sequence_number or 0,
                assignment.id,
            ),
        )
        if any(
            assignment.sequence_number is None
            or assignment.to_location_id is None
            or assignment.to_location is None
            for assignment in assignments
        ):
            raise SimulationScenarioConflictError(
                "Placed movements must have a sequence and target location"
            )

        locations = [
            location
            for assignment in assignments
            for location in (
                assignment.from_location,
                assignment.to_location,
            )
            if location is not None
        ]
        location_keys = self._location_sort_keys(locations)
        candidates: list[MoveBatchCandidate] = []
        for assignment in assignments:
            carton = assignment.carton
            packaging = carton.product_packaging
            product = packaging.product
            carton_type = packaging.carton_type
            if product.unit_weight_kg is None:
                raise SimulationScenarioConflictError(
                    f"Carton {carton.id} has no calculable weight"
                )
            weight = product.unit_weight_kg * carton.current_qty
            volume = (
                carton_type.outer_length_cm
                * carton_type.outer_width_cm
                * carton_type.outer_height_cm
                / self.cubic_centimeters_per_cubic_meter
            )
            dimensions = CartonDimensions(
                length_cm=carton_type.outer_length_cm,
                width_cm=carton_type.outer_width_cm,
                height_cm=carton_type.outer_height_cm,
            )
            source_placement = self._build_physical_placement(
                carton_id=carton.id,
                dimensions=dimensions,
                position_x_cm=assignment.from_position_x_cm,
                position_y_cm=assignment.from_position_y_cm,
                position_z_cm=assignment.from_position_z_cm,
                rotation_degrees=assignment.from_rotation_degrees,
                required=assignment.from_location_id is not None,
                placement_name="source",
            )
            target_placement = self._build_physical_placement(
                carton_id=carton.id,
                dimensions=dimensions,
                position_x_cm=assignment.proposed_position_x_cm,
                position_y_cm=assignment.proposed_position_y_cm,
                position_z_cm=assignment.proposed_position_z_cm,
                rotation_degrees=assignment.proposed_rotation_degrees,
                required=True,
                placement_name="target",
            )
            candidates.append(
                MoveBatchCandidate(
                    move_sequence=assignment.sequence_number,
                    carton_id=carton.id,
                    carton_number=carton.carton_number,
                    sku=product.sku,
                    weight_kg=weight.quantize(self.weight_quantum),
                    volume_m3=volume.quantize(self.volume_quantum),
                    from_location_id=assignment.from_location_id,
                    to_location_id=assignment.to_location_id,
                    from_location_key=(
                        location_keys[assignment.from_location_id]
                        if assignment.from_location_id is not None
                        else None
                    ),
                    to_location_key=location_keys[
                        assignment.to_location_id
                    ],
                    individual_distance_m=(
                        assignment.travel_distance_m or Decimal("0")
                    ),
                    individual_duration_seconds=(
                        assignment.estimated_duration_seconds
                        or Decimal("0")
                    ),
                    source_placement=source_placement,
                    target_placement=target_placement,
                )
            )
        return candidates

    @staticmethod
    def _build_physical_placement(
        *,
        carton_id: int,
        dimensions: CartonDimensions,
        position_x_cm: Decimal | None,
        position_y_cm: Decimal | None,
        position_z_cm: Decimal | None,
        rotation_degrees: int | None,
        required: bool,
        placement_name: str,
    ) -> PlacedCarton | None:
        placement_values = (
            position_x_cm,
            position_y_cm,
            position_z_cm,
            rotation_degrees,
        )
        if all(value is None for value in placement_values):
            if not required:
                return None
            raise SimulationScenarioConflictError(
                f"Carton {carton_id} has no complete {placement_name} placement"
            )
        if any(value is None for value in placement_values):
            raise SimulationScenarioConflictError(
                f"Carton {carton_id} has an incomplete "
                f"{placement_name} placement"
            )
        return build_placed_carton(
            carton_id=carton_id,
            dimensions=dimensions,
            position_x_cm=position_x_cm,
            position_y_cm=position_y_cm,
            position_z_cm=position_z_cm,
            rotation_degrees=rotation_degrees,
        )

    @staticmethod
    def _location_sort_keys(
        locations: list[WarehouseLocation],
    ) -> dict[int, tuple[int, int, int, int]]:
        aisle_ranks = {
            value: index
            for index, value in enumerate(
                sorted({location.aisle for location in locations}),
                start=1,
            )
        }
        bay_ranks = {
            value: index
            for index, value in enumerate(
                sorted({location.bay for location in locations}),
                start=1,
            )
        }
        level_ranks = {
            value: index
            for index, value in enumerate(
                sorted({location.level for location in locations}),
                start=1,
            )
        }
        slot_ranks = {
            value: index
            for index, value in enumerate(
                sorted({location.slot for location in locations}),
                start=1,
            )
        }
        return {
            location.id: (
                aisle_ranks[location.aisle],
                bay_ranks[location.bay],
                level_ranks[location.level],
                slot_ranks[location.slot],
            )
            for location in locations
        }

    @staticmethod
    def _locations_by_id(
        scenario: OptimizationRun,
    ) -> dict[int, WarehouseLocation]:
        return {
            location.id: location
            for assignment in scenario.assignments
            for location in (
                assignment.from_location,
                assignment.to_location,
            )
            if location is not None
        }

    def _build_batch_read(
        self,
        batch: PlannedMoveBatch,
        graph: WarehouseGraphSnapshot | None,
        locations: dict[int, WarehouseLocation],
    ) -> SimulationMoveBatchRead:
        distance = self._route_distance(batch, graph, locations)
        operational_items = batch.operational_items
        duration = (
            distance / self.walking_speed_m_per_second
            + self.handling_seconds_per_carton * len(operational_items)
        ).quantize(self.duration_quantum)
        return SimulationMoveBatchRead(
            sequence=batch.sequence,
            equipment_type=batch.equipment_type,
            carton_count=len(operational_items),
            total_weight_kg=batch.total_weight_kg.quantize(
                self.weight_quantum
            ),
            total_volume_m3=batch.total_volume_m3.quantize(
                self.volume_quantum
            ),
            estimated_distance_m=distance,
            estimated_duration_seconds=duration,
            capacity_utilization_percent=(
                batch.capacity_utilization_percent
            ),
            move_sequences=[
                item.move_sequence for item in operational_items
            ],
            staged_move_sequences=list(batch.staged_move_sequences),
            finalized_move_sequences=list(batch.finalized_move_sequences),
            items=[
                self._build_item_read(item) for item in operational_items
            ],
            stops=[
                SimulationMoveBatchStopRead(
                    sequence=stop.sequence,
                    type=stop.type,
                    location_id=stop.location_id,
                    carton_ids=list(stop.carton_ids),
                )
                for stop in batch.stops
            ],
            reasons=list(batch.reasons),
            requires_staging_buffer=batch.requires_staging_buffer,
        )

    @staticmethod
    def _build_item_read(
        item: MoveBatchCandidate,
    ) -> SimulationMoveBatchItemRead:
        return SimulationMoveBatchItemRead(
            move_sequence=item.move_sequence,
            carton_id=item.carton_id,
            carton_number=item.carton_number,
            sku=item.sku,
            weight_kg=item.weight_kg,
            volume_m3=item.volume_m3,
            from_location_id=item.from_location_id,
            to_location_id=item.to_location_id,
        )

    def _route_distance(
        self,
        batch: PlannedMoveBatch,
        graph: WarehouseGraphSnapshot | None,
        locations: dict[int, WarehouseLocation],
    ) -> Decimal:
        if not batch.stops:
            return Decimal("0")
        distance = self._distance_from_dispatch(
            batch.stops[0].location_id,
            graph,
            locations,
        )
        for previous, current in zip(batch.stops, batch.stops[1:]):
            distance += self._distance_between_locations(
                previous.location_id,
                current.location_id,
                graph,
                locations,
            )
        distance += self._distance_from_dispatch(
            batch.stops[-1].location_id,
            graph,
            locations,
        )
        return distance.quantize(self.distance_quantum)

    @staticmethod
    def _distance_from_dispatch(
        location_id: int,
        graph: WarehouseGraphSnapshot | None,
        locations: dict[int, WarehouseLocation],
    ) -> Decimal:
        if graph is not None:
            try:
                path = graph.path_from_dispatch(location_id)
                return Decimal(str(path.distance_m))
            except (
                WarehouseGraphLocationNotFoundError,
                ValueError,
            ):
                pass
        return locations[location_id].distance_from_dispatch_m

    @staticmethod
    def _distance_between_locations(
        first_id: int,
        second_id: int,
        graph: WarehouseGraphSnapshot | None,
        locations: dict[int, WarehouseLocation],
    ) -> Decimal:
        if first_id == second_id:
            return Decimal("0")
        if graph is not None:
            try:
                path = graph.path_between_locations(first_id, second_id)
                return Decimal(str(path.distance_m))
            except (
                WarehouseGraphLocationNotFoundError,
                ValueError,
            ):
                pass
        first = locations[first_id]
        second = locations[second_id]
        return abs(
            first.distance_from_dispatch_m
            - second.distance_from_dispatch_m
        )

    def _load_graph(self) -> WarehouseGraphSnapshot | None:
        try:
            return self.graph_service.load_snapshot()
        except WarehouseGraphDataError:
            return None
