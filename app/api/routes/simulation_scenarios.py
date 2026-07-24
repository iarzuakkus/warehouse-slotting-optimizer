"""Simulation scenario endpoints for alternative warehouse placements."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.simulation_scenario import (
    SimulationBatchAnimationRead,
    SimulationMoveBatchListRead,
    SimulationMoveBatchRead,
    SimulationMoveListRead,
    SimulationMoveRead,
    SimulationScenarioCreate,
    SimulationScenarioRead,
    SimulationScenarioStatus,
    SimulationScenarioUpdate,
)
from app.schemas.warehouse_rack import WarehouseRackSceneRead
from app.services.simulation_move_batch import (
    SimulationMoveBatchNotFoundError,
    SimulationMoveBatchService,
)
from app.services.simulation_scenario import (
    SimulationScenarioConflictError,
    SimulationScenarioExecutionError,
    SimulationScenarioNotFoundError,
    SimulationScenarioService,
)


router = APIRouter(
    prefix="/simulation-scenarios",
    tags=["simulation-scenarios"],
)


def get_simulation_scenario_service(
    db: Session = Depends(get_db),
) -> SimulationScenarioService:
    return SimulationScenarioService(db)


def get_simulation_move_batch_service(
    db: Session = Depends(get_db),
) -> SimulationMoveBatchService:
    return SimulationMoveBatchService(db)


@router.get("", response_model=list[SimulationScenarioRead])
def list_simulation_scenarios(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    scenario_status: SimulationScenarioStatus | None = Query(
        default=None,
        alias="status",
    ),
    service: SimulationScenarioService = Depends(
        get_simulation_scenario_service
    ),
) -> list[SimulationScenarioRead]:
    return service.list_scenarios(offset, limit, scenario_status)


@router.post(
    "",
    response_model=SimulationScenarioRead,
    status_code=status.HTTP_201_CREATED,
)
def create_simulation_scenario(
    data: SimulationScenarioCreate,
    service: SimulationScenarioService = Depends(
        get_simulation_scenario_service
    ),
) -> SimulationScenarioRead:
    try:
        return service.create_scenario(data)
    except SimulationScenarioConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get("/{scenario_id}", response_model=SimulationScenarioRead)
def get_simulation_scenario(
    scenario_id: int = Path(gt=0),
    service: SimulationScenarioService = Depends(
        get_simulation_scenario_service
    ),
) -> SimulationScenarioRead:
    try:
        return service.get_scenario(scenario_id)
    except SimulationScenarioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.patch("/{scenario_id}", response_model=SimulationScenarioRead)
def update_simulation_scenario(
    data: SimulationScenarioUpdate,
    scenario_id: int = Path(gt=0),
    service: SimulationScenarioService = Depends(
        get_simulation_scenario_service
    ),
) -> SimulationScenarioRead:
    try:
        return service.update_scenario(scenario_id, data)
    except SimulationScenarioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SimulationScenarioConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post("/{scenario_id}/run", response_model=SimulationScenarioRead)
def run_simulation_scenario(
    scenario_id: int = Path(gt=0),
    service: SimulationScenarioService = Depends(
        get_simulation_scenario_service
    ),
) -> SimulationScenarioRead:
    try:
        return service.run_scenario(scenario_id)
    except SimulationScenarioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SimulationScenarioConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except SimulationScenarioExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get(
    "/{scenario_id}/scene",
    response_model=list[WarehouseRackSceneRead],
)
def get_simulation_scenario_scene(
    scenario_id: int = Path(gt=0),
    step: int | None = Query(default=None, ge=0),
    service: SimulationScenarioService = Depends(
        get_simulation_scenario_service
    ),
) -> list[WarehouseRackSceneRead]:
    try:
        return service.get_scene(scenario_id, step)
    except SimulationScenarioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SimulationScenarioConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/{scenario_id}/batch-scene",
    response_model=list[WarehouseRackSceneRead],
)
def get_simulation_scenario_batch_scene(
    scenario_id: int = Path(gt=0),
    batch_step: int = Query(alias="step", ge=0),
    service: SimulationMoveBatchService = Depends(
        get_simulation_move_batch_service
    ),
) -> list[WarehouseRackSceneRead]:
    try:
        return service.get_batch_scene(scenario_id, batch_step)
    except SimulationScenarioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SimulationScenarioConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/{scenario_id}/moves",
    response_model=SimulationMoveListRead,
)
def list_simulation_scenario_moves(
    scenario_id: int = Path(gt=0),
    service: SimulationScenarioService = Depends(
        get_simulation_scenario_service
    ),
) -> SimulationMoveListRead:
    try:
        return service.get_moves(scenario_id)
    except SimulationScenarioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SimulationScenarioConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/{scenario_id}/moves/{sequence}",
    response_model=SimulationMoveRead,
)
def get_simulation_scenario_move(
    scenario_id: int = Path(gt=0),
    sequence: int = Path(gt=0),
    service: SimulationScenarioService = Depends(
        get_simulation_scenario_service
    ),
) -> SimulationMoveRead:
    try:
        return service.get_move(scenario_id, sequence)
    except SimulationScenarioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SimulationScenarioConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/{scenario_id}/move-batches",
    response_model=SimulationMoveBatchListRead,
)
def list_simulation_move_batches(
    scenario_id: int = Path(gt=0),
    service: SimulationMoveBatchService = Depends(
        get_simulation_move_batch_service
    ),
) -> SimulationMoveBatchListRead:
    try:
        return service.get_move_batches(scenario_id)
    except SimulationScenarioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SimulationScenarioConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/{scenario_id}/move-batches/{sequence}/animation",
    response_model=SimulationBatchAnimationRead,
)
def get_simulation_move_batch_animation(
    scenario_id: int = Path(gt=0),
    sequence: int = Path(gt=0),
    service: SimulationMoveBatchService = Depends(
        get_simulation_move_batch_service
    ),
) -> SimulationBatchAnimationRead:
    try:
        return service.get_batch_animation(scenario_id, sequence)
    except (
        SimulationScenarioNotFoundError,
        SimulationMoveBatchNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SimulationScenarioConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/{scenario_id}/move-batches/{sequence}",
    response_model=SimulationMoveBatchRead,
)
def get_simulation_move_batch(
    scenario_id: int = Path(gt=0),
    sequence: int = Path(gt=0),
    service: SimulationMoveBatchService = Depends(
        get_simulation_move_batch_service
    ),
) -> SimulationMoveBatchRead:
    try:
        return service.get_move_batch(scenario_id, sequence)
    except (
        SimulationScenarioNotFoundError,
        SimulationMoveBatchNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SimulationScenarioConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_simulation_scenario(
    scenario_id: int = Path(gt=0),
    service: SimulationScenarioService = Depends(
        get_simulation_scenario_service
    ),
) -> None:
    try:
        service.delete_scenario(scenario_id)
    except SimulationScenarioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SimulationScenarioConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
