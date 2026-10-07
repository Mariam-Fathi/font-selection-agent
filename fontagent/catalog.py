"""The Google Fonts catalogue: a dated snapshot of the public metadata, with lookups.

The agent used to search a hand-written list of 40 fonts. This module replaces it with
the full catalogue (about 1,950 families), loaded from a snapshot committed to the repo
so that benchmark results are reproducible. `refresh_snapshot()` rebuilds it.
"""

from __future__ import annotations

import difflib
import json
import urllib.request
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

METADATA_URL = "https://fonts.google.com/metadata/fonts"
SNAPSHOT_PATH = Path(__file__).parent / "data" / "google_fonts_catalog.json"
CSS_API = "https://fonts.googleapis.com/css2"

# The metadata's category names, mapped to the CSS generic family each one falls back to.
CATEGORIES = {
    "Sans Serif": "sans-serif",
    "Serif": "serif",
    "Display": "display",
    "Handwriting": "handwriting",
    "Monospace": "monospace",
}
GENERIC_FALLBACK = {
    "sans-serif": "sans-serif",
    "serif": "serif",
    "display": "sans-serif",
    "handwriting": "cursive",
    "monospace": "monospace",
}


@dataclass(frozen=True)
class FontFamily:
    family: str
    category: str  # one of CATEGORIES' values
    subsets: tuple[str, ...]
    weights: tuple[int, ...]  # upright weights available
    italic_weights: tuple[int, ...]
    axes: tuple[str, ...]  # variable-font axis tags, e.g. ("wght", "wdth")
    popularity: int  # rank: 1 is the most used family

    def supports(self, subset: str) -> bool:
        return subset in self.subsets

    @property
    def has_bold(self) -> bool:
        return any(w >= 600 for w in self.weights)

    def match_weights(self, needed: set[int], italic: bool = False) -> list[int]:
        """The available weights closest to each weight the page uses.

        CSS picks the nearest face anyway, but requesting a weight the family doesn't
        have makes the CSS API return an error, so we only ask for faces that exist.
        """
        available = self.italic_weights if italic else self.weights
        if not available:
            return []
        return sorted({min(available, key=lambda w: (abs(w - n), w)) for n in needed or {400}})

    def css_url(self, weights: set[int] | None = None, italic: bool = False) -> str:
        """A Google Fonts CSS2 URL that loads exactly the faces the page needs."""
        name = quote_plus(self.family)
        upright = self.match_weights(weights or {400})
        # Italic-only families (e.g. Molle) have no upright face to ask for.
        slanted = (self.match_weights(weights or {400}, italic=True)
                   if italic or not upright else [])
        if slanted:
            pairs = [f"0,{w}" for w in upright] + [f"1,{w}" for w in slanted]
            spec = f":ital,wght@{';'.join(pairs)}"
        elif upright and upright != [400]:
            spec = f":wght@{';'.join(map(str, upright))}"
        else:
            spec = ""
        return f"{CSS_API}?family={name}{spec}&display=block"

    @property
    def fallback(self) -> str:
        return GENERIC_FALLBACK[self.category]


def _parse_family(raw: dict) -> FontFamily:
    keys = list(raw["fonts"])
    return FontFamily(
        family=raw["family"],
        category=CATEGORIES.get(raw["category"], "display"),
        subsets=tuple(s for s in raw["subsets"] if s != "menu"),
        weights=tuple(sorted(int(k) for k in keys if k.isdigit())),
        italic_weights=tuple(sorted(int(k[:-1]) for k in keys if k.endswith("i"))),
        axes=tuple(a["tag"] for a in raw.get("axes", [])),
        popularity=raw["popularity"],
    )


def refresh_snapshot(path: Path = SNAPSHOT_PATH) -> int:
    """Download the public metadata and write a trimmed, dated snapshot."""
    with urllib.request.urlopen(METADATA_URL, timeout=60) as resp:
        text = resp.read().decode("utf-8")
    if text.startswith(")]}'"):  # the endpoint has used an anti-JSON-hijacking prefix
        text = text[4:]
    families = [_parse_family(f) for f in json.loads(text)["familyMetadataList"]]
    payload = {
        "source": METADATA_URL,
        "snapshot_date": date.today().isoformat(),
        "families": [
            [f.family, f.category, list(f.subsets), list(f.weights),
             list(f.italic_weights), list(f.axes), f.popularity]
            for f in sorted(families, key=lambda f: f.popularity)
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    load_catalog.cache_clear()
    return len(families)


class Catalog:
    def __init__(self, families: list[FontFamily], snapshot_date: str):
        self.families = families
        self.snapshot_date = snapshot_date
        self._by_name = {f.family.lower(): f for f in families}

    def __len__(self) -> int:
        return len(self.families)

    def get(self, name: str) -> FontFamily | None:
        return self._by_name.get(name.strip().lower())

    def suggest(self, name: str, n: int = 3) -> list[str]:
        """Closest real family names, for a typo or a renamed font."""
        hits = difflib.get_close_matches(name.lower(), self._by_name, n=n, cutoff=0.6)
        return [self._by_name[h].family for h in hits]

    def search(
        self,
        category: str | None = None,
        query: str | None = None,
        subset: str | None = None,
        needs_bold: bool = False,
        limit: int = 20,
    ) -> list[FontFamily]:
        """Families matching every filter given, most popular first."""
        category = normalize_category(category) if category else None
        query = query.lower().strip() if query else None
        hits = [
            f for f in self.families
            if (category is None or f.category == category)
            and (query is None or query in f.family.lower())
            and (subset is None or f.supports(subset))
            and (not needs_bold or f.has_bold)
        ]
        return hits[:limit]


def normalize_category(category: str) -> str:
    key = category.lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "sans": "sans-serif", "sansserif": "sans-serif", "sans-serif": "sans-serif",
        "serif": "serif", "display": "display", "monospace": "monospace", "mono": "monospace",
        "handwriting": "handwriting", "handwritten": "handwriting", "script": "handwriting",
    }
    if key not in aliases:
        raise ValueError(f"Unknown category {category!r}; use one of {sorted(GENERIC_FALLBACK)}")
    return aliases[key]


@lru_cache(maxsize=1)
def load_catalog(path: Path = SNAPSHOT_PATH) -> Catalog:
    data = json.loads(path.read_text(encoding="utf-8"))
    families = [
        FontFamily(family, category, tuple(subsets), tuple(weights), tuple(italics),
                   tuple(axes), popularity)
        for family, category, subsets, weights, italics, axes, popularity in data["families"]
    ]
    return Catalog(families, data["snapshot_date"])


if __name__ == "__main__":
    print(f"Wrote {refresh_snapshot()} families to {SNAPSHOT_PATH}")
