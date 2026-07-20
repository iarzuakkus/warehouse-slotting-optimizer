"""Depo konumu CRUD endpoint'leri."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.warehouse_location import (
    WarehouseLocationCreate,
    WarehouseLocationRead,
    WarehouseLocationUpdate,
)
from app.services.warehouse_location import (
    DuplicateWarehouseLocationError,
    WarehouseLocationNotFoundError,
    WarehouseLocationRackCapacityError,
    WarehouseLocationRackNotFoundError,
    WarehouseLocationService,
)


router = APIRouter(prefix="/warehouse-locations", tags=["warehouse-locations"])


def get_location_service(db: Session = Depends(get_db)) -> WarehouseLocationService:
    return WarehouseLocationService(db)


@router.get("", response_model=list[WarehouseLocationRead])
def list_locations(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    service: WarehouseLocationService = Depends(get_location_service),
) -> list[WarehouseLocationRead]:
    return service.list_locations(offset=offset, limit=limit)


@router.get("/{location_id}", response_model=WarehouseLocationRead)
def get_location(
    location_id: int,
    service: WarehouseLocationService = Depends(get_location_service),
) -> WarehouseLocationRead:
    try:
        return service.get_location(location_id)
    except WarehouseLocationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("", response_model=WarehouseLocationRead, status_code=status.HTTP_201_CREATED)
def create_location(
    data: WarehouseLocationCreate,
    service: WarehouseLocationService = Depends(get_location_service),
) -> WarehouseLocationRead:
    try:
        return service.create_location(data)
    except WarehouseLocationRackNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WarehouseLocationRackCapacityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DuplicateWarehouseLocationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/{location_id}", response_model=WarehouseLocationRead)
def update_location(
    location_id: int,
    data: WarehouseLocationUpdate,
    service: WarehouseLocationService = Depends(get_location_service),
) -> WarehouseLocationRead:
    try:
        return service.update_location(location_id, data)
    except WarehouseLocationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WarehouseLocationRackCapacityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DuplicateWarehouseLocationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/{location_id}", response_model=WarehouseLocationRead)
def deactivate_location(
    location_id: int,
    service: WarehouseLocationService = Depends(get_location_service),
) -> WarehouseLocationRead:
    try:
        return service.deactivate_location(location_id)
    except WarehouseLocationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
