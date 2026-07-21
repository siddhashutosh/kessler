"""KESSLER backend application factory."""
from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import settings
from app.core.exceptions import KesslerError
from app.core.logging_config import request_id_var, setup_logging
from app.service.conjunction_service import ConjunctionService

setup_logging()
logger = logging.getLogger("kessler")


async def _scheduler(app: FastAPI) -> None:
    """In-process refresh loop; replaced by EventBridge in the AWS phase."""
    while True:
        await asyncio.sleep(settings.pipeline_refresh_seconds)
        try:
            await asyncio.to_thread(app.state.conjunctions.refresh)
        except Exception as exc:  # scheduler must survive any failure
            logger.error("Scheduled pipeline refresh failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.conjunctions = ConjunctionService()
    logger.info(
        "KESSLER %s starting (data_mode=%s)",
        settings.version,
        app.state.conjunctions.data_mode,
    )
    try:
        await asyncio.to_thread(app.state.conjunctions.refresh)
    except Exception as exc:
        logger.error("Initial pipeline refresh failed (continuing): %s", exc)
    task = asyncio.create_task(_scheduler(app))
    yield
    task.cancel()
    app.state.conjunctions.spacetrack.close()
    logger.info("KESSLER shutdown complete")


app = FastAPI(
    title="KESSLER",
    description="Open Orbital Conjunction Assessment & Risk Toolkit. "
    "Orbital data courtesy of Space-Track.org and CelesTrak.",
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = uuid.uuid4().hex[:12]
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-Id"] = rid
    return response


def _envelope(code: str, message: str, detail, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "detail": detail,
                "request_id": request_id_var.get(),
            }
        },
    )


@app.exception_handler(KesslerError)
async def kessler_error_handler(request: Request, exc: KesslerError):
    logger.warning("%s: %s (detail=%s)", exc.code, exc.message, exc.detail)
    return _envelope(exc.code, exc.message, exc.detail, exc.http_status)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return _envelope("VALIDATION_ERROR", "Request validation failed",
                     exc.errors(), 422)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return _envelope("INTERNAL_ERROR", "An internal error occurred", None, 500)


app.include_router(router)

# Single-service deployment: when the built UI is present (ui/dist), serve it
# from this process — API routes above always win; unknown paths fall back to
# the SPA's index.html for client-side routing.
_UI_DIST = Path(__file__).resolve().parents[2] / "ui" / "dist"

if (_UI_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=_UI_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        candidate = (_UI_DIST / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and candidate.is_relative_to(_UI_DIST.resolve())
        ):
            return FileResponse(candidate)
        return FileResponse(_UI_DIST / "index.html")

    logger.info("Serving UI from %s", _UI_DIST)
else:

    @app.get("/")
    def root():
        return {
            "name": "KESSLER",
            "version": settings.version,
            "docs": "/docs",
            "api": "/api/v1",
            "attribution": "Orbital data courtesy of Space-Track.org (USSPACECOM) and CelesTrak.",
        }
