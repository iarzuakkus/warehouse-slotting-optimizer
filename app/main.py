"""FastAPI uygulamasının başlangıç noktası."""

from fastapi import FastAPI

from app.api.routes.carton_types import router as carton_types_router
from app.api.routes.health import router as health_router
from app.api.routes.products import router as products_router


app = FastAPI(title="Warehouse Slotting Optimizer")
app.include_router(health_router)
app.include_router(products_router)
app.include_router(carton_types_router)
