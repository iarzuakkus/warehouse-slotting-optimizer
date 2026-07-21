"""Optimizasyon çalışması tablosu için SQLAlchemy işlemleri."""

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import ProductPackaging
from app.models.inventory import Carton, WarehouseLocation
from app.models.optimization import OptimizationAssignment, OptimizationRun
from app.schemas.optimization_run import (
    OptimizationRunCreate,
    OptimizationRunStatus,
    OptimizationRunUpdate,
)
from app.schemas.simulation_scenario import (
    SimulationScenarioCreate,
    SimulationScenarioUpdate,
)


class OptimizationRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, run_id: int) -> OptimizationRun | None:
        return self.session.get(OptimizationRun, run_id)

    def get_scenario_by_id(
        self,
        scenario_id: int,
        *,
        for_update: bool = False,
    ) -> OptimizationRun | None:
        assignment_loader = selectinload(OptimizationRun.assignments)
        statement = (
            select(OptimizationRun)
            .where(
                OptimizationRun.id == scenario_id,
                OptimizationRun.name.is_not(None),
            )
            .options(
                assignment_loader.joinedload(
                    OptimizationAssignment.carton
                )
                .joinedload(Carton.product_packaging)
                .joinedload(ProductPackaging.product),
                assignment_loader.joinedload(
                    OptimizationAssignment.carton
                )
                .joinedload(Carton.product_packaging)
                .joinedload(ProductPackaging.carton_type),
                assignment_loader.joinedload(
                    OptimizationAssignment.from_location
                ).joinedload(WarehouseLocation.rack),
                assignment_loader.joinedload(
                    OptimizationAssignment.to_location
                ).joinedload(WarehouseLocation.rack),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def list_runs(
        self,
        offset: int = 0,
        limit: int = 100,
        run_status: OptimizationRunStatus | None = None,
    ) -> list[OptimizationRun]:
        statement = select(OptimizationRun).order_by(
            OptimizationRun.created_at.desc(),
            OptimizationRun.id.desc(),
        )
        if run_status is not None:
            statement = statement.where(OptimizationRun.status == run_status)
        statement = statement.offset(offset).limit(limit)
        return list(self.session.scalars(statement))

    def list_scenarios(
        self,
        offset: int = 0,
        limit: int = 100,
        scenario_status: OptimizationRunStatus | None = None,
    ) -> list[OptimizationRun]:
        statement = (
            select(OptimizationRun)
            .where(OptimizationRun.name.is_not(None))
            .order_by(
                OptimizationRun.created_at.desc(),
                OptimizationRun.id.desc(),
            )
        )
        if scenario_status is not None:
            statement = statement.where(
                OptimizationRun.status == scenario_status
            )
        statement = statement.offset(offset).limit(limit)
        return list(self.session.scalars(statement))

    def create(self, data: OptimizationRunCreate) -> OptimizationRun:
        run = OptimizationRun(**data.model_dump())
        self.session.add(run)
        self.session.flush()
        return run

    def create_scenario(
        self,
        data: SimulationScenarioCreate,
    ) -> OptimizationRun:
        parameters = data.model_dump(
            mode="json",
            exclude={"name", "seed", "algorithm_name"},
        )
        scenario = OptimizationRun(
            name=data.name,
            seed=data.seed,
            algorithm_name=data.algorithm_name,
            parameters=parameters,
        )
        self.session.add(scenario)
        self.session.flush()
        return scenario

    def update(
        self,
        run: OptimizationRun,
        data: OptimizationRunUpdate,
    ) -> OptimizationRun:
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(run, field, value)

        self.session.flush()
        return run

    def update_scenario(
        self,
        scenario: OptimizationRun,
        data: SimulationScenarioUpdate,
    ) -> OptimizationRun:
        changes = data.model_dump(mode="json", exclude_unset=True)
        for column_name in ("name", "seed", "algorithm_name"):
            if column_name in changes:
                setattr(scenario, column_name, changes.pop(column_name))

        if changes:
            scenario.parameters = {**scenario.parameters, **changes}

        self.session.flush()
        return scenario

    def replace_assignments(
        self,
        scenario: OptimizationRun,
        assignments: Sequence[OptimizationAssignment],
    ) -> list[OptimizationAssignment]:
        self.session.execute(
            delete(OptimizationAssignment).where(
                OptimizationAssignment.optimization_run_id == scenario.id
            )
        )
        scenario.assignments = []
        for assignment in assignments:
            assignment.optimization_run_id = scenario.id
        self.session.add_all(assignments)
        self.session.flush()
        return list(assignments)

    def save(self, scenario: OptimizationRun) -> OptimizationRun:
        self.session.add(scenario)
        self.session.flush()
        return scenario

    def delete_scenario(self, scenario: OptimizationRun) -> None:
        self.session.delete(scenario)
        self.session.flush()
