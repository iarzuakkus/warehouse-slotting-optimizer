"""Depo yürüyüş grafı rota endpoint'leri."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.warehouse_graph import (
    BetweenLocationsRouteRead,
    DispatchRouteRead,
    WarehouseGraphLayoutRead,
)
from app.services.warehouse_graph import (
    WarehouseGraphDataError,
    WarehouseGraphLocationNotFoundError,
    WarehouseGraphService,
)


router = APIRouter(prefix="/warehouse-graph", tags=["warehouse-graph"])


def get_warehouse_graph_service(
    db: Session = Depends(get_db),
) -> WarehouseGraphService:
    return WarehouseGraphService(db)


@router.get("/layout", response_model=WarehouseGraphLayoutRead)
def get_warehouse_graph_layout(
    include_locations: bool = Query(default=False),
    service: WarehouseGraphService = Depends(get_warehouse_graph_service),
) -> WarehouseGraphLayoutRead:
    try:
        snapshot = service.load_snapshot()
        return snapshot.build_layout(include_locations=include_locations)
    except WarehouseGraphDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/routes/from-dispatch/{location_id}",
    response_model=DispatchRouteRead,
)
def get_route_from_dispatch(
    location_id: int = Path(gt=0),
    service: WarehouseGraphService = Depends(get_warehouse_graph_service),
) -> DispatchRouteRead:
    try:
        snapshot = service.load_snapshot()
        path = snapshot.path_from_dispatch(location_id)
        return DispatchRouteRead(
            location_id=location_id,
            distance_m=path.distance_m,
            nodes=list(path.nodes),
        )
    except WarehouseGraphLocationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except WarehouseGraphDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/routes/between-locations",
    response_model=BetweenLocationsRouteRead,
)
def get_route_between_locations(
    start_location_id: int = Query(gt=0),
    destination_location_id: int = Query(gt=0),
    service: WarehouseGraphService = Depends(get_warehouse_graph_service),
) -> BetweenLocationsRouteRead:
    try:
        snapshot = service.load_snapshot()
        path = snapshot.path_between_locations(
            start_location_id,
            destination_location_id,
        )
        return BetweenLocationsRouteRead(
            start_location_id=start_location_id,
            destination_location_id=destination_location_id,
            distance_m=path.distance_m,
            nodes=list(path.nodes),
        )
    except WarehouseGraphLocationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except WarehouseGraphDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
