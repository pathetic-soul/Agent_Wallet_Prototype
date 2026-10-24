from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings
from app.services.telemetry import TelemetryLog


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Agent Wallet API",
        version="0.1.0",
        description="ERC-4337 relay and event API for the Agent Wallet prototype.",
    )
    app.state.telemetry = TelemetryLog()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(router)
    return app


app = create_app()

