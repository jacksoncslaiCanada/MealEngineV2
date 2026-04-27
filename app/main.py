"""FastAPI application entry point."""
from __future__ import annotations

import base64
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from app.routes.cron import router as cron_router
from app.routes.ingredients import router as ingredients_router
from app.routes.plans import router as plans_router
from app.routes.recipes import router as recipes_router
from app.routes.subscribe import router as subscribe_router
from app.routes.ui import router as ui_router

logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    """Run any pending Alembic migrations on startup."""
    try:
        from alembic.config import Config
        from alembic import command

        cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
        command.upgrade(cfg, "head")
        logger.info("startup: Alembic migrations applied")
    except Exception as exc:
        logger.error("startup: Alembic migration failed — %s", exc)
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_migrations()
    yield


_UNGATED_PATHS = {"/health", "/health/pdf"}


class SiteGateMiddleware(BaseHTTPMiddleware):
    """Require HTTP Basic Auth when SITE_PASSWORD is set.

    Exempt paths (health checks) bypass the gate so Railway's
    health probes always succeed.
    """

    async def dispatch(self, request: Request, call_next):
        from app.config import settings  # late import — avoids circular at module load

        if not settings.site_password:
            return await call_next(request)

        if request.url.path in _UNGATED_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8", errors="replace")
                username, _, password = decoded.partition(":")
                user_ok = secrets.compare_digest(username, settings.site_username)
                pass_ok = secrets.compare_digest(password, settings.site_password)
                if user_ok and pass_ok:
                    return await call_next(request)
            except Exception:
                pass

        return Response(
            content="Access restricted — site is in pre-launch mode.",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="MealEngine"'},
        )


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="MealEngine API",
    description="Recipe ingestion and ingredient extraction API.",
    version="2.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SiteGateMiddleware)

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

app.include_router(recipes_router)
app.include_router(ingredients_router)
app.include_router(plans_router)
app.include_router(subscribe_router)
app.include_router(ui_router)
app.include_router(cron_router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui/meal-plan")


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/pdf", tags=["meta"])
def health_pdf() -> dict:
    """Minimal WeasyPrint smoke test — confirms system libraries are present."""
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string="<h1>MealEngine PDF test</h1>").write_pdf()
        return {"status": "ok", "pdf_bytes": len(pdf_bytes)}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
