"""Fiziksel koli endpoint'leri."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.carton import CartonCreate, CartonRead, CartonStatus, CartonUpdate
from app.services.carton import (
    CartonNotFoundError,
    CartonQuantityError,
    CartonReferenceNotFoundError,
    CartonService,
    DuplicateCartonNumberError,
    InactiveCartonReferenceError,
)


router = APIRouter(prefix="/cartons", tags=["cartons"])


def get_carton_service(db: Session = Depends(get_db)) -> CartonService:
    return CartonService(db)


@router.get("", response_model=list[CartonRead])
def list_cartons(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    carton_status: CartonStatus | None = Query(default=None, alias="status"),
    location_id: int | None = Query(default=None, gt=0),
    service: CartonService = Depends(get_carton_service),
) -> list[CartonRead]:
    return service.list_cartons(
        offset=offset,
        limit=limit,
        carton_status=carton_status,
        location_id=location_id,
    )


@router.get("/{carton_id}", response_model=CartonRead)
def get_carton(
    carton_id: int,
    service: CartonService = Depends(get_carton_service),
) -> CartonRead:
    try:
        return service.get_carton(carton_id)
    except CartonNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("", response_model=CartonRead, status_code=status.HTTP_201_CREATED)
def create_carton(
    data: CartonCreate,
    service: CartonService = Depends(get_carton_service),
) -> CartonRead:
    try:
        return service.create_carton(data)
    except CartonReferenceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (DuplicateCartonNumberError, InactiveCartonReferenceError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CartonQuantityError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.patch("/{carton_id}", response_model=CartonRead)
def update_carton(
    carton_id: int,
    data: CartonUpdate,
    service: CartonService = Depends(get_carton_service),
) -> CartonRead:
    try:
        return service.update_carton(carton_id, data)
    except CartonNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CartonQuantityError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
