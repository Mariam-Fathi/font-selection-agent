"""Turn the benchmark CSVs into the tables used in the case study.

    python -m benchmark.analyze          # writes results/phase1_report.md
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from fontagent.catalog import load_catalog

RESULTS = Path(__file__).parent / "results"
FIDELITY = ["font_not_loaded", "glyph_fallback", "synthetic_bold", "synthetic_italic",
            "icon_font_overridden"]
LAYOUT_ERRORS = ["clipped_text", "control_wraps", "horizontal_overflow"]
ICON_PAGES = ["landing", "pricing", "dashboard"]  # fixtures that use an icon font
ITALIC_PAGES = ["landing"]  # fixtures with italic text


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion k/n."""
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def rate(mask: pd.Series) -> str:
    k, n = int(mask.sum()), int(mask.size)
    lo, hi = wilson(k, n)
    return f"{k / n:.1%} ({k}/{n}; 95% CI {lo:.1%} to {hi:.1%})"


def table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(map(str, row)) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def fidelity_section(df: pd.DataFrame) -> list[str]:
    catalog = load_catalog()
    df = df[df.in_catalog].copy()
    df["has_bold"] = df.has_bold.astype(str).eq("True")
    df["has_italic"] = df.font.map(lambda n: bool(catalog.get(n).italic_weights))
    v1fonts = df[df.source == "v1_list"]
    out = ["## 1. Does the screenshot show the font it claims to?", "",
           f"Fonts from the original list that are still in the catalogue "
           f"({v1fonts.font.nunique()} of 40), on all pages at both widths.", "",
           "**Problems the pipeline caused.** The font has the face, but the screenshot "
           "doesn't show it.", ""]
    rows = []
    for strategy in ("v1", "v2"):
        p = v1fonts[v1fonts.strategy == strategy]
        fake_bold = (p.synthetic_bold > 0) & p.has_bold
        fake_italic = (p.synthetic_italic > 0) & p.has_italic
        icons = p.icon_font_overridden > 0
        rows.append({"pipeline": strategy,
                     "bold faked though a bold face exists": rate(fake_bold),
                     "italic faked though an italic face exists": rate(fake_italic),
                     "icons replaced by text (pages with icons)": rate(icons[p.fixture.isin(ICON_PAGES)]),
                     "any": rate(fake_bold | fake_italic | icons)})
    out += [table(pd.DataFrame(rows)), ""]
    p = v1fonts[v1fonts.strategy == "v2"]
    limits = {
        "no bold face, page has bold text": (~p.has_bold, p.synthetic_bold > 0),
        "no italic face, page has italic text": (~p.has_italic & p.fixture.isin(ITALIC_PAGES),
                                                 p.synthetic_italic > 0),
        "no Arabic glyphs, page has Arabic": (~p.supports_arabic.astype(str).eq("True")
                                              & (p.fixture == "bilingual"), p.glyph_fallback > 0),
    }
    rows = [{"real limit of the font": name, "renders": int(mask.sum()),
             "v2 told the user": rate(flag[mask]), "v1 told the user": "0% (no checks)"}
            for name, (mask, flag) in limits.items()]
    out += ["**Real limits of the font.** No pipeline can fix these; the question is whether "
            "the user is told.", "", table(pd.DataFrame(rows)), ""]
    return out


def agreement_section(df: pd.DataFrame) -> list[str]:
    v2 = df[(df.strategy == "v2") & df.in_catalog].copy()
    v2["has_bold"] = v2.has_bold.astype(str).eq("True")
    v2["supports_arabic"] = v2.supports_arabic.astype(str).eq("True")
    out = ["## 2. Does the verifier agree with an independent source of truth?", "",
           "The catalogue says which scripts and weights each family has; the verifier only "
           "looks at what Chrome drew. They are independent, so agreement validates the verifier.", ""]
    arabic = v2[v2.fixture == "bilingual"].drop_duplicates(["font", "viewport"])
    flagged = arabic.glyph_fallback > 0
    truth = ~arabic.supports_arabic
    out += [f"**Arabic coverage** (bilingual page, {len(arabic)} renders): verifier and catalogue "
            f"agree on {rate(flagged == truth)}.", "",
            table(pd.crosstab(truth.rename("catalogue: no Arabic"),
                              flagged.rename("verifier: fallback found")).reset_index()), ""]
    bold = v2.drop_duplicates(["font", "fixture", "viewport"])
    flagged = bold.synthetic_bold > 0
    truth = ~bold.has_bold
    out += [f"**Faked bold** ({len(bold)} renders): verifier and catalogue agree on "
            f"{rate(flagged == truth)}.", ""]
    return out


def layout_section(df: pd.DataFrame) -> list[str]:
    v2 = df[(df.strategy == "v2") & df.in_catalog]
    broken = v2[LAYOUT_ERRORS].sum(axis=1) > 0
    out = ["## 3. How often does a real font break a real layout?", "",
           f"With the v2 pipeline, {rate(broken)} of renders introduced at least one layout error "
           "(cut-off text, a wrapping button or label, or sideways scrolling).", ""]
    rows = []
    for (category, viewport), part in v2.groupby(["category", "viewport"]):
        rows.append({"category": category, "viewport": viewport,
                     "renders with a layout error": rate(part[LAYOUT_ERRORS].sum(axis=1) > 0)})
    out += [table(pd.DataFrame(rows)), ""]
    return out


def planted_section() -> list[str]:
    runs = {"development seeds 0-9": RESULTS / "planted_summary.json",
            "held-out seeds 10-19": RESULTS / "planted_heldout_summary.json"}
    runs = {name: json.loads(p.read_text(encoding="utf-8")) for name, p in runs.items() if p.exists()}
    if not runs:
        return []
    rows = []
    for i, first in enumerate(next(iter(runs.values()))):
        row = {"trial": first["trial"], "expected": "detected" if first["planted"] else "no false alarm"}
        for name, summary in runs.items():
            s = summary[i]
            lo, hi = wilson(s["passed"], s["n"])
            row[name] = f"{s['passed']}/{s['n']} (95% CI {lo:.0%} to {hi:.0%})"
        rows.append(row)
    return ["## 0. Does the detector find planted flaws?", "",
            "The detector was fixed using the development seeds; the held-out seeds were run "
            "once, afterwards, with no changes.", "", table(pd.DataFrame(rows)), ""]


def main() -> None:
    sections = ["# Phase 1 benchmark report", "",
                "Generated by `python -m benchmark.analyze`. Do not edit by hand.", ""]
    sections += planted_section()
    audit = RESULTS / "render_audit.csv"
    if audit.exists():
        df = pd.read_csv(audit)
        df["in_catalog"] = df.in_catalog.astype(bool)
        sections += fidelity_section(df) + agreement_section(df) + layout_section(df)
    report = "\n".join(sections)
    (RESULTS / "phase1_report.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
