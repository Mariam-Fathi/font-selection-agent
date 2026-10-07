"""Agent tool: render the user's page with candidate fonts and report what really happened."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fontagent.catalog import load_catalog
from fontagent.render import VIEWPORTS, Renderer, page_url

OUTPUT_DIR = Path("previews")


async def take_font_screenshots(
    font_names: list[str],
    file_path: str | None = None,
    url: str | None = None,
    scope: str = "all",
    viewport: str = "desktop",
) -> dict[str, Any]:
    """Render a page with each font, verify it rendered, and check the layout.

    The page is never modified on disk: the font is applied inside the browser only.
    Each font's render is compared with the page's original fonts, and problems are
    reported per font: the font didn't load, some text fell back to another font
    (missing glyphs, e.g. Arabic), bold or italic was faked by the browser, buttons or
    labels wrapped or got cut off, or the page started scrolling sideways.

    Args:
        font_names: Exact Google Fonts family names, e.g. ["Inter", "Lora"]. Use names
            returned by search_google_fonts.
        file_path: Path to a local .html file. Use this or url.
        url: URL of a running app (e.g. "http://localhost:3000") for React, Vue and other
            frameworks.
        scope: Which text gets the font: "all", "headings" or "body".
        viewport: "desktop" (1280x800) or "mobile" (390x844).

    Returns:
        {"status": "success", "original_screenshot": "...",
         "results": [{"font": "Inter", "verdict": "clean" | "warnings" | "broken",
                      "glyph_coverage": 1.0, "screenshot": "...", "issues": [...]}],
         "clean": ["Inter"], "broken": [...], "not_found": {...}}
    """
    if viewport not in VIEWPORTS:
        return {"status": "error", "message": f"viewport must be one of {sorted(VIEWPORTS)}"}
    if scope not in {"all", "headings", "body"}:
        return {"status": "error", "message": "scope must be 'all', 'headings' or 'body'"}
    catalog = load_catalog()
    known = [catalog.get(n).family for n in font_names if catalog.get(n)]
    not_found = {n: catalog.suggest(n) for n in font_names if not catalog.get(n)}
    out_dir = OUTPUT_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        with page_url(file_path, url) as target:
            async with Renderer(viewport=viewport) as renderer:
                baseline, results = await renderer.compare(
                    target, known, scope=scope, screenshot_dir=out_dir)
    except (FileNotFoundError, ValueError) as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:  # browser or network failure: tell the agent, don't crash it
        return {"status": "error", "message": f"Rendering failed: {e}"}
    summaries = [r.summary() for r in results]
    return {
        "status": "success",
        "screenshots_folder": str(out_dir),
        "original_screenshot": baseline.screenshot,
        "results": summaries,
        "clean": [s["font"] for s in summaries if s["verdict"] == "clean"],
        "with_warnings": [s["font"] for s in summaries if s["verdict"] == "warnings"],
        "broken": [s["font"] for s in summaries if s["verdict"] == "broken"],
        "not_found": {name: {"did_you_mean": hints} for name, hints in not_found.items()},
    }
