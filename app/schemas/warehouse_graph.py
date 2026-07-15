"""Depo yürüyüş grafı API cevap şemaları."""

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
