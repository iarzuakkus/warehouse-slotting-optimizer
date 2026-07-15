"""Koli taşıma ve konum geçmişi endpoint'leri."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.carton_location_history import (
    CartonLocationHistoryRead,
    CartonMovementCreate,
)
from app.services.carton_location_history import (
    CartonLocationHistoryService,
    CartonMovementConflictError,
    CartonMovementLocationNotFoundError,
    CartonMovementNotFoundError,
)


router = APIRouter(
    prefix="/cartons/{carton_id}/movements",
    tags=["carton-location-history"],
)


def get_carton_location_history_service(
    db: Session = Depends(get_db),
) -> CartonLocationHistoryService:
    return CartonLocationHistoryService(db)


@router.get("", response_model=list[CartonLocationHistoryRead])
def list_carton_movements(
    carton_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    service: CartonLocationHistoryService = Depends(
        get_carton_location_history_service
    ),
) -> list[CartonLocationHistoryRead]:
    try:
        return service.list_history(carton_id, offset, limit)
    except CartonMovementNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{history_id}", response_model=CartonLocationHistoryRead)
def get_carton_movement(
    carton_id: int,
    history_id: int,
    service: CartonLocationHistoryService = Depends(
        get_carton_location_history_service
    ),
) -> CartonLocationHistoryRead:
    try:
        return service.get_history(carton_id, history_id)
    except CartonMovementNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "",
    response_model=CartonLocationHistoryRead,
    status_code=status.HTTP_201_CREATED,
)
def move_carton(
    carton_id: int,
    data: CartonMovementCreate,
    service: CartonLocationHistoryService = Depends(
        get_carton_location_history_service
    ),
) -> CartonLocationHistoryRead:
    try:
        return service.move_carton(carton_id, data)
    except (
        CartonMovementLocationNotFoundError,
        CartonMovementNotFoundError,
    ) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CartonMovementConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
