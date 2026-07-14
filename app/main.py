"""FastAPI uygulamasının başlangıç noktası."""

from fastapi import FastAPI

from app.api.routes.health import router as health_router


app = FastAPI(title="Warehouse Slotting Optimizer")
app.include_router(health_router)
