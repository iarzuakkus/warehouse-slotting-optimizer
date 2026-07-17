"""FastAPI uygulamasının başlangıç noktası."""

from fastapi import FastAPI

from app.api.routes.carton_allocations import router as carton_allocations_router
from app.api.routes.carton_location_history import router as carton_location_history_router
from app.api.routes.cartons import router as cartons_router
from app.api.routes.carton_types import router as carton_types_router
from app.api.routes.health import router as health_router
from app.api.routes.orders import router as orders_router
from app.api.routes.order_lines import router as order_lines_router
from app.api.routes.optimization_assignments import router as optimization_assignments_router
from app.api.routes.optimization_runs import router as optimization_runs_router
from app.api.routes.pick_operations import router as pick_operations_router
from app.api.routes.product_packaging import router as product_packaging_router
from app.api.routes.products import router as products_router
from app.api.routes.warehouse_graph import router as warehouse_graph_router
from app.api.routes.warehouse_locations import router as warehouse_locations_router
from app.api.routes.warehouse_racks import router as warehouse_racks_router


app = FastAPI(title="Warehouse Slotting Optimizer")
app.include_router(health_router)
app.include_router(products_router)
app.include_router(carton_types_router)
app.include_router(warehouse_locations_router)
app.include_router(warehouse_racks_router)
app.include_router(warehouse_graph_router)
app.include_router(product_packaging_router)
app.include_router(cartons_router)
app.include_router(orders_router)
app.include_router(order_lines_router)
app.include_router(carton_allocations_router)
app.include_router(pick_operations_router)
app.include_router(carton_location_history_router)
app.include_router(optimization_runs_router)
app.include_router(optimization_assignments_router)

# python -m uvicorn app.main:app --reload
