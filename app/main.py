"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI

from app.routes.ingredients import router as ingredients_router
from app.routes.recipes import router as recipes_router

app = FastAPI(
    title="MealEngine API",
    description="Recipe ingestion and ingredient extraction API.",
    version="2.0.0",
)

app.include_router(recipes_router)
app.include_router(ingredients_router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
