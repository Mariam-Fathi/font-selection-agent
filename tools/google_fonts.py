"""Agent tool: search the Google Fonts catalogue."""

from __future__ import annotations

from typing import Any

from fontagent.catalog import load_catalog, normalize_category


def search_google_fonts(
    category: str | None = None,
    query: str | None = None,
    subset: str | None = None,
    needs_bold: bool = False,
    limit: int = 8,
) -> dict[str, Any]:
    """Search the full Google Fonts catalogue (about 1,950 families), most popular first.

    Args:
        category: One of "sans-serif", "serif", "display", "handwriting", "monospace".
        query: Text to match in the family name, e.g. "mono" or "slab".
        subset: A script the font must support, e.g. "arabic", "cyrillic", "greek".
            Use this when the page has text outside basic Latin.
        needs_bold: Only return families with a real bold face (weight 600 or more).
            Use this when the page has bold headings or buttons.
        limit: Maximum number of fonts to return.

    Returns:
        {"status": "success", "count": 3, "catalog_snapshot": "2026-10-07",
         "fonts": [{"name": "Inter", "category": "sans-serif", "weights": [100, ..., 900],
                    "has_italic": true, "popularity_rank": 3, "scripts": [...]}]}
    """
    catalog = load_catalog()
    try:
        hits = catalog.search(category=normalize_category(category) if category else None,
                              query=query, subset=subset, needs_bold=needs_bold, limit=limit)
    except ValueError as e:
        return {"status": "error", "message": str(e), "fonts": []}
    return {
        "status": "success",
        "count": len(hits),
        "catalog_snapshot": catalog.snapshot_date,
        "fonts": [
            {
                "name": f.family,
                "category": f.category,
                "weights": list(f.weights),
                "has_italic": bool(f.italic_weights),
                "popularity_rank": f.popularity,
                "scripts": [s for s in f.subsets if not s.endswith("-ext")],
            }
            for f in hits
        ],
    }
