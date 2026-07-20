"""Optimizasyon yerleşim önerisi iş kuralları."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.optimization import OptimizationAssignment, OptimizationRun
from app.repositories.carton import CartonRepository
from app.repositories.optimization_assignment import (
    OptimizationAssignmentRepository,
)
from app.repositories.optimization_run import OptimizationRunRepository
from app.repositories.warehouse_location import WarehouseLocationRepository
from app.schemas.optimization_assignment import OptimizationAssignmentCreate
from app.services.carton_placement import CartonPlacementService


class OptimizationAssignmentNotFoundError(Exception):
    """Çalışma veya yerleşim önerisi bulunamadığında kullanılır."""


class OptimizationAssignmentReferenceNotFoundError(Exception):
    """Koli veya hedef raf bulunamadığında kullanılır."""


class DuplicateOptimizationAssignmentError(Exception):
    """Aynı çalışma içinde koli için ikinci öneri oluşturulduğunda kullanılır."""


class OptimizationAssignmentConflictError(Exception):
    """Çalışma, koli veya raf durumu öneriyi engellediğinde kullanılır."""


class OptimizationAssignmentService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = OptimizationAssignmentRepository(session)
        self.run_repository = OptimizationRunRepository(session)
        self.carton_repository = CartonRepository(session)
        self.location_repository = WarehouseLocationRepository(session)
        self.placement_service = CartonPlacementService(session)

    def _get_run(self, run_id: int) -> OptimizationRun:
        run = self.run_repository.get_by_id(run_id)
        if run is None:
            raise OptimizationAssignmentNotFoundError(
                f"Optimization run {run_id} not found"
            )
        return run

    def _get_assignment(
        self,
        run_id: int,
        assignment_id: int,
    ) -> OptimizationAssignment:
        assignment = self.repository.get_by_id(assignment_id)
        if assignment is None or assignment.optimization_run_id != run_id:
            raise OptimizationAssignmentNotFoundError(
                f"Assignment {assignment_id} not found in optimization run {run_id}"
            )
        return assignment

    @staticmethod
    def _ensure_running(run: OptimizationRun) -> None:
        if run.status != "running":
            raise OptimizationAssignmentConflictError(
                f"Assignments cannot change while run status is {run.status}"
            )

    def list_assignments(
        self,
        run_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[OptimizationAssignment]:
        self._get_run(run_id)
        return self.repository.list_by_run(run_id, offset, limit)

    def get_assignment(
        self,
        run_id: int,
        assignment_id: int,
    ) -> OptimizationAssignment:
        self._get_run(run_id)
        return self._get_assignment(run_id, assignment_id)

    def create_assignment(
        self,
        run_id: int,
        data: OptimizationAssignmentCreate,
    ) -> OptimizationAssignment:
        run = self._get_run(run_id)
        self._ensure_running(run)

        carton = self.carton_repository.get_by_id(data.carton_id)
        if carton is None:
            raise OptimizationAssignmentReferenceNotFoundError(
                f"Carton {data.carton_id} not found"
            )
        if carton.status in {"depleted", "quarantined"}:
            raise OptimizationAssignmentConflictError(
                f"Carton {carton.id} cannot be assigned while status is {carton.status}"
            )

        target = self.location_repository.get_by_id(data.to_location_id)
        if target is None:
            raise OptimizationAssignmentReferenceNotFoundError(
                f"Warehouse location {data.to_location_id} not found"
            )
        if not target.is_active:
            raise OptimizationAssignmentConflictError(
                f"Warehouse location {target.id} is inactive"
            )
        if carton.current_location_id == target.id:
            raise OptimizationAssignmentConflictError(
                "Carton is already in the proposed location"
            )
        if self.repository.get_by_run_and_carton(run.id, carton.id):
            raise DuplicateOptimizationAssignmentError(
                "Carton already has an assignment in this optimization run"
            )

        packaging = carton.product_packaging
        excluded_location_ids = (
            {carton.current_location_id}
            if carton.current_location_id is not None
            else set()
        )
        placement = self.placement_service.find_available_placement(
            product=packaging.product,
            carton_type=packaging.carton_type,
            current_qty=carton.current_qty,
            preferred_location_id=data.to_location_id,
            exclude_carton_id=carton.id,
            excluded_location_ids=excluded_location_ids,
        )
        if placement is None:
            raise OptimizationAssignmentConflictError(
                "No warehouse location has enough physical and weight capacity"
            )
        effective_data = data.model_copy(
            update={"to_location_id": placement.location_id}
        )

        try:
            assignment = self.repository.create(
                run_id=run.id,
                from_location_id=carton.current_location_id,
                data=effective_data,
            )
            assignment.proposed_position_x_cm = placement.position_x_cm
            assignment.proposed_position_y_cm = placement.position_y_cm
            assignment.proposed_position_z_cm = placement.position_z_cm
            assignment.proposed_rotation_degrees = placement.rotation_degrees
            self.session.flush()
            self.session.commit()
            self.session.refresh(assignment)
            return assignment
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateOptimizationAssignmentError(
                "Assignment violates a database rule"
            ) from exc

    def delete_assignment(self, run_id: int, assignment_id: int) -> None:
        run = self._get_run(run_id)
        self._ensure_running(run)
        assignment = self._get_assignment(run_id, assignment_id)
        self.repository.delete(assignment)
        self.session.commit()
