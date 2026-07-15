"""Sipariş satırı CRUD endpoint'leri."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.order_line import OrderLineCreate, OrderLineRead, OrderLineUpdate
from app.services.order_line import (
    DuplicateOrderLineError,
    OrderLineConflictError,
    OrderLineNotFoundError,
    OrderLineReferenceNotFoundError,
    OrderLineService,
)


router = APIRouter(prefix="/orders/{order_id}/lines", tags=["order-lines"])


def get_order_line_service(db: Session = Depends(get_db)) -> OrderLineService:
    return OrderLineService(db)


@router.get("", response_model=list[OrderLineRead])
def list_order_lines(
    order_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    service: OrderLineService = Depends(get_order_line_service),
) -> list[OrderLineRead]:
    try:
        return service.list_lines(order_id, offset, limit)
    except OrderLineReferenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{line_id}", response_model=OrderLineRead)
def get_order_line(
    order_id: int,
    line_id: int,
    service: OrderLineService = Depends(get_order_line_service),
) -> OrderLineRead:
    try:
        return service.get_line(order_id, line_id)
    except (OrderLineReferenceNotFoundError, OrderLineNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=OrderLineRead, status_code=status.HTTP_201_CREATED)
def create_order_line(
    order_id: int,
    data: OrderLineCreate,
    service: OrderLineService = Depends(get_order_line_service),
) -> OrderLineRead:
    try:
        return service.create_line(order_id, data)
    except OrderLineReferenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (DuplicateOrderLineError, OrderLineConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/{line_id}", response_model=OrderLineRead)
def update_order_line(
    order_id: int,
    line_id: int,
    data: OrderLineUpdate,
    service: OrderLineService = Depends(get_order_line_service),
) -> OrderLineRead:
    try:
        return service.update_line(order_id, line_id, data)
    except (OrderLineReferenceNotFoundError, OrderLineNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OrderLineConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order_line(
    order_id: int,
    line_id: int,
    service: OrderLineService = Depends(get_order_line_service),
) -> None:
    try:
        service.delete_line(order_id, line_id)
    except (OrderLineReferenceNotFoundError, OrderLineNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OrderLineConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
