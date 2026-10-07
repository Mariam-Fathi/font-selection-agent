"""Render real fonts on real pages with the v1 and v2 pipelines and record what happened.

Fonts: the 40 the original agent offered, plus a stratified random sample from the
full catalogue (equal numbers per category). Pages: the fixtures in benchmark/fixtures,
at desktop and mobile widths. One row per render goes to results/render_audit.csv.

    python -m benchmark.render_audit --per-category 16 --seed 7
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import random
from pathlib import Path

from fontagent.catalog import GENERIC_FALLBACK, load_catalog
from fontagent.render import Renderer, page_url

FIXTURES = Path(__file__).parent / "fixtures"
RESULTS = Path(__file__).parent / "results"

# The original agent's hard-coded list, kept verbatim for the comparison.
V1_FONTS = [
    "Comforter Brush", "Dancing Script", "Caveat", "Kalam", "Permanent Marker", "Indie Flower",
    "Shadows Into Light", "Satisfy", "Amatic SC", "Pacifico", "Shadows Into Light Two",
    "Caveat Brush", "Gloria Hallelujah", "Handlee", "Playfair Display", "Merriweather", "Lora",
    "PT Serif", "Crimson Text", "Libre Baskerville", "Source Serif Pro", "Bitter", "Roboto",
    "Open Sans", "Lato", "Montserrat", "Poppins", "Raleway", "Inter", "Nunito", "Oswald",
    "Bebas Neue", "Righteous", "Bangers", "Fredoka One", "Lobster", "Roboto Mono",
    "Source Code Pro", "Fira Code", "Courier Prime",
]
ISSUE_KINDS = ["font_not_loaded", "glyph_fallback", "synthetic_bold", "synthetic_italic",
               "icon_font_overridden", "clipped_text", "text_spill", "control_wraps",
               "heading_wraps", "horizontal_overflow", "page_height_change"]


def sample_fonts(per_category: int, seed: int) -> list[tuple[str, str]]:
    """(family, source) pairs: the v1 list plus a seeded sample per category."""
    catalog = load_catalog()
    rng = random.Random(seed)
    v1 = set(V1_FONTS)
    picked = [(name, "v1_list") for name in V1_FONTS]
    for category in sorted(GENERIC_FALLBACK):
        pool = [f.family for f in catalog.families if f.category == category and f.family not in v1]
        picked += [(name, "catalog_sample") for name in rng.sample(pool, per_category)]
    return picked


async def run(fonts: list[tuple[str, str]], concurrency: int) -> list[dict]:
    catalog = load_catalog()
    rows: list[dict] = []
    gate = asyncio.Semaphore(concurrency)
    for viewport in ("desktop", "mobile"):
        async with Renderer(viewport=viewport) as renderer:
            for fixture in sorted(FIXTURES.glob("*.html")):
                with page_url(str(fixture)) as url:
                    baseline = await renderer.render(url, None)

                    async def one(name: str, source: str, strategy: str, url: str = url,
                                  baseline=baseline, fixture: Path = fixture,
                                  viewport: str = viewport) -> None:
                        async with gate:
                            try:
                                r = await renderer.render(url, name, strategy=strategy,
                                                          baseline=baseline)
                            except Exception as e:  # a render failure is a result too
                                print(f"  failed: {name} {strategy} ({e})")
                                return
                        family = catalog.get(name)
                        kinds = [i.kind for i in r.issues]
                        rows.append({
                            "font": name, "source": source,
                            "category": family.category if family else "unknown",
                            "in_catalog": family is not None,
                            "popularity": family.popularity if family else "",
                            "has_bold": family.has_bold if family else "",
                            "supports_arabic": family.supports("arabic") if family else "",
                            "fixture": fixture.stem, "viewport": viewport, "strategy": strategy,
                            "css_status": r.css_status, "loaded_faces": len(r.loaded_faces),
                            "glyph_coverage": round(r.coverage.get("coverage", 0.0), 4),
                            "verdict": r.summary()["verdict"], "seconds": r.seconds,
                            **{k: kinds.count(k) for k in ISSUE_KINDS},
                        })

                    await asyncio.gather(*(one(n, s, strat) for n, s in fonts
                                           for strat in ("v1", "v2")))
                print(f"{viewport} {fixture.stem}: {len(rows)} renders so far")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--per-category", type=int, default=16)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--only", nargs="+", metavar="FONT",
                        help="re-render just these fonts and replace their rows in the CSV")
    args = parser.parse_args()
    fonts = sample_fonts(args.per_category, args.seed)
    if args.only:
        fonts = [(name, source) for name, source in fonts if name in args.only]
    rows = asyncio.run(run(fonts, args.concurrency))
    RESULTS.mkdir(exist_ok=True)
    if args.only:
        with open(RESULTS / "render_audit.csv", newline="", encoding="utf-8") as f:
            kept = [r for r in csv.DictReader(f) if r["font"] not in args.only]
        rows = kept + rows
    rows.sort(key=lambda r: (r["viewport"], r["fixture"], str(r["font"]), r["strategy"]))
    with open(RESULTS / "render_audit.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {RESULTS / 'render_audit.csv'}")


if __name__ == "__main__":
    main()
