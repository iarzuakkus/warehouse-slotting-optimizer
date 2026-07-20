"""Warehouse rack summary and detail endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.warehouse_rack import (
    WarehouseRackRead,
    WarehouseRackSceneRead,
    WarehouseRackSummaryRead,
)
from app.services.warehouse_rack import (
    WarehouseRackNotFoundError,
    WarehouseRackService,
)


router = APIRouter(prefix="/warehouse-racks", tags=["warehouse-racks"])


def get_warehouse_rack_service(
    db: Session = Depends(get_db),
) -> WarehouseRackService:
    return WarehouseRackService(db)


@router.get("", response_model=list[WarehouseRackSummaryRead])
def list_warehouse_racks(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    service: WarehouseRackService = Depends(get_warehouse_rack_service),
) -> list[WarehouseRackSummaryRead]:
    return service.list_racks(offset=offset, limit=limit)


@router.get("/scene", response_model=list[WarehouseRackSceneRead])
def list_warehouse_rack_scene(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    service: WarehouseRackService = Depends(get_warehouse_rack_service),
) -> list[WarehouseRackSceneRead]:
    return service.list_scene_racks(offset=offset, limit=limit)


@router.get("/{aisle}/{bay}", response_model=WarehouseRackRead)
def get_warehouse_rack(
    aisle: str = Path(min_length=1, max_length=30),
    bay: str = Path(min_length=1, max_length=30),
    service: WarehouseRackService = Depends(get_warehouse_rack_service),
) -> WarehouseRackRead:
    try:
        return service.get_rack(aisle, bay)
    except WarehouseRackNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
