"""Warehouse rack detail endpoint."""

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.warehouse_rack import WarehouseRackRead
from app.services.warehouse_rack import (
    WarehouseRackNotFoundError,
    WarehouseRackService,
)


router = APIRouter(prefix="/warehouse-racks", tags=["warehouse-racks"])


def get_warehouse_rack_service(
    db: Session = Depends(get_db),
) -> WarehouseRackService:
    return WarehouseRackService(db)


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
