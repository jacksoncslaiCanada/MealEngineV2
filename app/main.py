"""FastAPI application entry point."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.routes.ingredients import router as ingredients_router
from app.routes.plans import router as plans_router
from app.routes.recipes import router as recipes_router
from app.routes.ui import router as ui_router

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="MealEngine API",
    description="Recipe ingestion and ingredient extraction API.",
    version="2.0.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

app.include_router(recipes_router)
app.include_router(ingredients_router)
app.include_router(plans_router)
app.include_router(ui_router)


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
