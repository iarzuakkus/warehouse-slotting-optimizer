"""Sipariş üst bilgisi endpoint'leri."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.order import OrderCreate, OrderRead, OrderStatus, OrderUpdate
from app.services.order import (
    DuplicateOrderNumberError,
    InvalidOrderDateError,
    InvalidOrderStatusTransitionError,
    OrderNotFoundError,
    OrderService,
)


router = APIRouter(prefix="/orders", tags=["orders"])


def get_order_service(db: Session = Depends(get_db)) -> OrderService:
    return OrderService(db)


@router.get("", response_model=list[OrderRead])
def list_orders(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    order_status: OrderStatus | None = Query(default=None, alias="status"),
    service: OrderService = Depends(get_order_service),
) -> list[OrderRead]:
    return service.list_orders(
        offset=offset,
        limit=limit,
        order_status=order_status,
    )


@router.get("/{order_id}", response_model=OrderRead)
def get_order(
    order_id: int,
    service: OrderService = Depends(get_order_service),
) -> OrderRead:
    try:
        return service.get_order(order_id)
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(
    data: OrderCreate,
    service: OrderService = Depends(get_order_service),
) -> OrderRead:
    try:
        return service.create_order(data)
    except DuplicateOrderNumberError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InvalidOrderDateError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.patch("/{order_id}", response_model=OrderRead)
def update_order(
    order_id: int,
    data: OrderUpdate,
    service: OrderService = Depends(get_order_service),
) -> OrderRead:
    try:
        return service.update_order(order_id, data)
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidOrderStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InvalidOrderDateError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
