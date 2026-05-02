"""Render Gumroad listing cover images (1600×900 PNG) for all products.

Usage:
    python scripts/render_listing_covers.py [--out-dir listing-covers]

Outputs one PNG per product:
    theme-pack--{slug}.png
    weekly-anchor--{slug}.png
    bundle--{slug}.png
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent.parent / "app" / "templates"

THEMES = [
    {
        "slug":         "asian-kitchen",
        "name":         "Asian Kitchen",
        "tagline":      "Bold, fragrant flavours from across Asia.",
        "accent_color": "#c2522a",
    },
    {
        "slug":         "mexican-fiesta",
        "name":         "Mexican Fiesta",
        "tagline":      "Vibrant, bold, and made for sharing.",
        "accent_color": "#2a8a3a",
    },
    {
        "slug":         "light-and-fresh",
        "name":         "Light & Fresh",
        "tagline":      "Clean, nourishing meals that don't feel like a compromise.",
        "accent_color": "#4a8a5a",
    },
    {
        "slug":         "quick-cook",
        "name":         "Quick Cook",
        "tagline":      "Dinner on the table in 30 minutes or less.",
        "accent_color": "#d4762a",
    },
    {
        "slug":         "comfort-food",
        "name":         "Comfort Food",
        "tagline":      "Hearty, warming dishes that feel like a hug.",
        "accent_color": "#8b4a2a",
    },
    {
        "slug":         "mediterranean",
        "name":         "Mediterranean",
        "tagline":      "Sun-drenched flavours from the shores of the Mediterranean.",
        "accent_color": "#2a6b9c",
    },
    {
        "slug":         "italian-classics",
        "name":         "Italian Classics",
        "tagline":      "Timeless Italian recipes done properly.",
        "accent_color": "#8b2a2a",
    },
    {
        "slug":         "middle-eastern",
        "name":         "Middle Eastern",
        "tagline":      "Ancient spices, vibrant flavours, generous tables.",
        "accent_color": "#c4823a",
    },
    {
        "slug":         "high-protein",
        "name":         "High Protein",
        "tagline":      "Fuel your body without compromising on flavour.",
        "accent_color": "#4a6b8a",
    },
    {
        "slug":         "one-pan",
        "name":         "One Pan",
        "tagline":      "Maximum flavour, minimal washing up.",
        "accent_color": "#7a5a3a",
    },
]

BUNDLES = [
    {
        "slug":          "world-flavours",
        "name":          "World Flavours",
        "accent_color":  "#c4823a",
        "bundle_themes": ["Asian Kitchen", "Mexican Fiesta", "Middle Eastern"],
        "tagline":       "",
    },
    {
        "slug":          "weeknight-essentials",
        "name":          "Weeknight Essentials",
        "accent_color":  "#d4762a",
        "bundle_themes": ["Quick Cook", "One Pan", "Comfort Food"],
        "tagline":       "",
    },
    {
        "slug":          "eat-smart",
        "name":          "Eat Smart",
        "accent_color":  "#4a8a5a",
        "bundle_themes": ["Light & Fresh", "High Protein", "Mediterranean"],
        "tagline":       "",
    },
]


def _name_px(name: str) -> str:
    """Scale headline font size to prevent overflow for longer names."""
    length = len(name)
    if length <= 9:
        return "128px"
    if length <= 14:
        return "104px"
    return "80px"


def _render_png(html: str, width: int, height: int) -> bytes:
    from playwright.sync_api import sync_playwright

    launch_kwargs: dict = {}
    ep = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
    if not ep:
        # Common Railway / Docker path — set env var to override
        fallback = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        if Path(fallback).exists():
            ep = fallback
    if ep:
        launch_kwargs["executable_path"] = ep

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html, wait_until="networkidle")
        png = page.screenshot(full_page=False, type="png")
        browser.close()

    return png


def render_all(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    tmpl = env.get_template("listing_cover.html")

    # ── Theme Pack covers ──────────────────────────────────────────────────
    for t in THEMES:
        ctx = {
            "accent_color":   t["accent_color"],
            "price":          "$6.99",
            "price_label":    "",
            "product_label":  "Dinner Pack",
            "theme_name":     t["name"],
            "name_size":      _name_px(t["name"]),
            "tagline":        t["tagline"],
            "bundle_themes":  [],
            "includes":       ["3 Recipe Cards", "Shopping List", "Pantry Guide"],
            "bottom_note":    "Instant PDF download — print or save to your phone",
            "right_note":     "Instant PDF download",
        }
        html = tmpl.render(**ctx)
        png  = _render_png(html, 1600, 900)
        path = out_dir / f"theme-pack--{t['slug']}.png"
        path.write_bytes(png)
        print(f"  ✓  {path.name}")

    # ── Weekly Anchor covers ───────────────────────────────────────────────
    for t in THEMES:
        ctx = {
            "accent_color":   t["accent_color"],
            "price":          "$12.99",
            "price_label":    "",
            "product_label":  "Weekly Anchor",
            "theme_name":     t["name"],
            "name_size":      _name_px(t["name"]),
            "tagline":        t["tagline"],
            "bundle_themes":  [],
            "includes":       ["5 Recipe Cards", "Macro Guide", "Shopping List", "Pantry Guide"],
            "bottom_note":    "Instant PDF download — Mon–Fri fully planned",
            "right_note":     "Instant PDF download",
        }
        html = tmpl.render(**ctx)
        png  = _render_png(html, 1600, 900)
        path = out_dir / f"weekly-anchor--{t['slug']}.png"
        path.write_bytes(png)
        print(f"  ✓  {path.name}")

    # ── Bundle covers ──────────────────────────────────────────────────────
    for b in BUNDLES:
        ctx = {
            "accent_color":   b["accent_color"],
            "price":          "$19.99",
            "price_label":    "",
            "product_label":  "Bundle · 3 Dinner Packs",
            "theme_name":     b["name"],
            "name_size":      _name_px(b["name"]),
            "tagline":        "",
            "bundle_themes":  b["bundle_themes"],
            "includes":       ["9 Recipe Cards", "3 Shopping Lists", "Pantry Guides"],
            "bottom_note":    "Instant ZIP download — 3 complete packs",
            "right_note":     "Instant ZIP download",
        }
        html = tmpl.render(**ctx)
        png  = _render_png(html, 1600, 900)
        path = out_dir / f"bundle--{b['slug']}.png"
        path.write_bytes(png)
        print(f"  ✓  {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Gumroad listing cover PNGs")
    parser.add_argument("--out-dir", default="listing-covers", type=Path)
    args = parser.parse_args()

    print(f"Rendering 23 cover images → {args.out_dir}/")
    render_all(args.out_dir)
    print("Done.")


if __name__ == "__main__":
    main()
