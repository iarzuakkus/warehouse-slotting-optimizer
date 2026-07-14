"""Koli tipi CRUD endpoint'leri."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.carton_type import CartonTypeCreate, CartonTypeRead, CartonTypeUpdate
from app.services.carton_type import (
    CartonTypeNotFoundError,
    CartonTypeService,
    DuplicateCartonTypeCodeError,
)


router = APIRouter(prefix="/carton-types", tags=["carton-types"])


def get_carton_type_service(db: Session = Depends(get_db)) -> CartonTypeService:
    return CartonTypeService(db)


@router.get("", response_model=list[CartonTypeRead])
def list_carton_types(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    service: CartonTypeService = Depends(get_carton_type_service),
) -> list[CartonTypeRead]:
    return service.list_carton_types(offset=offset, limit=limit)


@router.get("/{carton_type_id}", response_model=CartonTypeRead)
def get_carton_type(
    carton_type_id: int,
    service: CartonTypeService = Depends(get_carton_type_service),
) -> CartonTypeRead:
    try:
        return service.get_carton_type(carton_type_id)
    except CartonTypeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("", response_model=CartonTypeRead, status_code=status.HTTP_201_CREATED)
def create_carton_type(
    data: CartonTypeCreate,
    service: CartonTypeService = Depends(get_carton_type_service),
) -> CartonTypeRead:
    try:
        return service.create_carton_type(data)
    except DuplicateCartonTypeCodeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/{carton_type_id}", response_model=CartonTypeRead)
def update_carton_type(
    carton_type_id: int,
    data: CartonTypeUpdate,
    service: CartonTypeService = Depends(get_carton_type_service),
) -> CartonTypeRead:
    try:
        return service.update_carton_type(carton_type_id, data)
    except CartonTypeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateCartonTypeCodeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/{carton_type_id}", response_model=CartonTypeRead)
def deactivate_carton_type(
    carton_type_id: int,
    service: CartonTypeService = Depends(get_carton_type_service),
) -> CartonTypeRead:
    try:
        return service.deactivate_carton_type(carton_type_id)
    except CartonTypeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
