from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from attendance.api.routes.auth import router as auth_router
from attendance.api.routes.documents import router as documents_router
from attendance.api.routes.exports import router as exports_router
from attendance.api.routes.health import router as health_router
from attendance.api.routes.queries import router as queries_router
from attendance.config import Settings, get_settings
from attendance.db.session import dispose_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    dispose_engine()


def create_app(settings: Settings | None = None) -> FastAPI:
    application_settings = settings or get_settings()
    application = FastAPI(
        title="Attendance Intelligence API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=application_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(documents_router)
    application.include_router(queries_router)
    application.include_router(exports_router)
    return application


app = create_app()
