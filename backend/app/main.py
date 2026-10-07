from fastapi import FastAPI
from app.api.routes import auth, health, products, inventory, events, dashboard, alerts
from app.core.config import settings
from app.db.mongodb import db, init_indexes
from fastapi.middleware.cors import CORSMiddleware
from pymongo import AsyncMongoClient
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    import certifi
    db.client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    await init_indexes()
    yield
    # Shutdown
    if db.client:
        await db.client.close()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.API_CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
