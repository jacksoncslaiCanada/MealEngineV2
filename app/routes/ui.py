"""UI routes — serves Jinja2 HTML templates for the browser-facing frontend."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from pathlib import Path

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("", response_class=RedirectResponse, include_in_schema=False)
def ui_root():
    """Redirect /ui → /ui/meal-plan (default view)."""
    return RedirectResponse(url="/ui/meal-plan")


@router.get("/meal-plan", response_class=HTMLResponse, include_in_schema=False)
def meal_plan_page(request: Request):
    return templates.TemplateResponse("meal_plan.html", {"request": request})


@router.get("/recipes", response_class=HTMLResponse, include_in_schema=False)
def recipes_page(request: Request):
    return templates.TemplateResponse("recipes.html", {"request": request})
