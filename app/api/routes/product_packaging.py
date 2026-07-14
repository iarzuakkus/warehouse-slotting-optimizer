"""Ürün paketleme CRUD endpoint'leri."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.product_packaging import (
    ProductPackagingCreate,
    ProductPackagingRead,
    ProductPackagingUpdate,
)
from app.services.product_packaging import (
    DuplicateProductPackagingError,
    InactivePackagingReferenceError,
    PackagingReferenceNotFoundError,
    ProductPackagingInUseError,
    ProductPackagingNotFoundError,
    ProductPackagingService,
)


router = APIRouter(prefix="/product-packaging", tags=["product-packaging"])


def get_packaging_service(db: Session = Depends(get_db)) -> ProductPackagingService:
    return ProductPackagingService(db)


@router.get("", response_model=list[ProductPackagingRead])
def list_packaging(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    product_id: int | None = Query(default=None, gt=0),
    service: ProductPackagingService = Depends(get_packaging_service),
) -> list[ProductPackagingRead]:
    return service.list_packaging(
        offset=offset,
        limit=limit,
        product_id=product_id,
    )


@router.get("/{packaging_id}", response_model=ProductPackagingRead)
def get_packaging(
    packaging_id: int,
    service: ProductPackagingService = Depends(get_packaging_service),
) -> ProductPackagingRead:
    try:
        return service.get_packaging(packaging_id)
    except ProductPackagingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("", response_model=ProductPackagingRead, status_code=status.HTTP_201_CREATED)
def create_packaging(
    data: ProductPackagingCreate,
    service: ProductPackagingService = Depends(get_packaging_service),
) -> ProductPackagingRead:
    try:
        return service.create_packaging(data)
    except PackagingReferenceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (InactivePackagingReferenceError, DuplicateProductPackagingError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/{packaging_id}", response_model=ProductPackagingRead)
def update_packaging(
    packaging_id: int,
    data: ProductPackagingUpdate,
    service: ProductPackagingService = Depends(get_packaging_service),
) -> ProductPackagingRead:
    try:
        return service.update_packaging(packaging_id, data)
    except (ProductPackagingNotFoundError, PackagingReferenceNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (InactivePackagingReferenceError, DuplicateProductPackagingError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/{packaging_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_packaging(
    packaging_id: int,
    service: ProductPackagingService = Depends(get_packaging_service),
) -> None:
    try:
        service.delete_packaging(packaging_id)
    except ProductPackagingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ProductPackagingInUseError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
