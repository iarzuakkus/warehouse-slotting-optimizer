"""Depo yürüyüş grafı API cevap şemaları."""

from typing import Literal

from pydantic import BaseModel, Field


class DispatchRouteRead(BaseModel):
    """Sevkiyat noktasından bir raf lokasyonuna hesaplanan rota."""

    location_id: int = Field(gt=0)
    distance_m: float = Field(ge=0)
    nodes: list[str] = Field(min_length=1)


class BetweenLocationsRouteRead(BaseModel):
    """İki raf lokasyonu arasında hesaplanan rota."""

    start_location_id: int = Field(gt=0)
    destination_location_id: int = Field(gt=0)
    distance_m: float = Field(ge=0)
    nodes: list[str] = Field(min_length=1)


class WarehouseGraphNodeRead(BaseModel):
    """Görselleştirilecek bir depo grafı düğümü."""

    id: str = Field(min_length=1)
    node_type: Literal["dispatch", "pickup", "location"]
    label: str = Field(min_length=1)
    x: float
    y: float
    location_id: int | None = Field(default=None, gt=0)


class WarehouseGraphEdgeRead(BaseModel):
    """Görselleştirilecek ağırlıklı depo grafı kenarı."""

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    distance_m: float = Field(gt=0)


class WarehouseGraphLayoutRead(BaseModel):
    """Depo grafının görselleştirme için düğüm ve kenar koleksiyonu."""

    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    nodes: list[WarehouseGraphNodeRead]
    edges: list[WarehouseGraphEdgeRead]
