"""FastAPI application entry point."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routes.ingredients import router as ingredients_router
from app.routes.plans import router as plans_router
from app.routes.recipes import router as recipes_router
from app.routes.ui import router as ui_router

app = FastAPI(
    title="MealEngine API",
    description="Recipe ingestion and ingredient extraction API.",
    version="2.0.0",
)

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


@app.get("/health/env", tags=["meta"])
def health_env() -> dict:
    """Show which environment variables are set (values masked)."""
    import os
    keys = ["ANTHROPIC_API_KEY", "DATABASE_URL", "YOUTUBE_API_KEY"]
    result = {
        k: ("set, length=" + str(len(os.environ[k]))) if k in os.environ else "NOT SET"
        for k in keys
    }
    # Also show any key whose name contains ANTHROPIC (catches typos/casing)
    result["_anthropic_scan"] = [
        k for k in os.environ if "anthropic" in k.lower()
    ]
    return result


@app.get("/health/pdf", tags=["meta"])
def health_pdf() -> dict:
    """Minimal WeasyPrint smoke test — confirms system libraries are present."""
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string="<h1>MealEngine PDF test</h1>").write_pdf()
        return {"status": "ok", "pdf_bytes": len(pdf_bytes)}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
