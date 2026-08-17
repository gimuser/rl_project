# main.py
import sys
from pathlib import Path

# إضافة مجلد backend للمسار الأساسي لـ Python لتفادي مشاكل الـ Imports
sys.path.append(str(Path(__file__).resolve().parent))

from fastapi import FastAPI
from app.api.router import router
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings

app = FastAPI(
    title="SOAR-RL-Agent API",
    version="1.0.0",
    description="Backend Central API for SOAR Reinforcement Learning Agent",
)

# Configure CORS for frontend dev servers and register routers
app.add_middleware(
    CORSMiddleware,
    allow_origins=getattr(settings, "api_allowed_origins", ["*"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Start API activity tracking (middleware + background monitor)
from app.services.api_activity import (
    init_api_status_store,
    api_activity_middleware,
    start_status_monitor,
    stop_status_monitor,
)

if settings.enable_api_activity_tracking:
    init_api_status_store(app)
    app.middleware("http")(api_activity_middleware)


@app.on_event("startup")
async def _startup_api_monitor():
    start_status_monitor(app)


@app.on_event("shutdown")
async def _shutdown_api_monitor():
    await stop_status_monitor(app)

# تسجيل الـ Routers الأساسية
app.include_router(router)


@app.get("/", tags=["Root"])
def root():
    return {"message": "Welcome to SOAR-RL-Agent API"}


if __name__ == "__main__":
    import uvicorn
    from app.config.settings import settings

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )