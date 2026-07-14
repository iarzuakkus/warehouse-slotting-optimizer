"""Ürün kataloğu CRUD endpoint'leri."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate
from app.services.product import (
    DuplicateProductSKUError,
    ProductNotFoundError,
    ProductService,
)


router = APIRouter(prefix="/products", tags=["products"])


def get_product_service(db: Session = Depends(get_db)) -> ProductService:
    return ProductService(db)


@router.get("", response_model=list[ProductRead])
def list_products(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    service: ProductService = Depends(get_product_service),
) -> list[ProductRead]:
    return service.list_products(offset=offset, limit=limit)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(
    product_id: int,
    service: ProductService = Depends(get_product_service),
) -> ProductRead:
    try:
        return service.get_product(product_id)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    data: ProductCreate,
    service: ProductService = Depends(get_product_service),
) -> ProductRead:
    try:
        return service.create_product(data)
    except DuplicateProductSKUError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int,
    data: ProductUpdate,
    service: ProductService = Depends(get_product_service),
) -> ProductRead:
    try:
        return service.update_product(product_id, data)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateProductSKUError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/{product_id}", response_model=ProductRead)
def deactivate_product(
    product_id: int,
    service: ProductService = Depends(get_product_service),
) -> ProductRead:
    try:
        return service.deactivate_product(product_id)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
