"""Build the Phase 2 test set: clean renders, and copies with one known flaw planted.

Fonts come from the Phase 1 audit (renders whose v2 verdict was clean), so each damaged
case differs from its clean twin only by the planted flaw. Screenshots are regenerated
deterministically and kept out of git; the manifest is committed.

    python -m benchmark.critic_cases
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from pathlib import Path

import pandas as pd

from benchmark import planted
from fontagent.catalog import load_catalog
from fontagent.render import Renderer, page_url

ROOT = Path(__file__).parent
FIXTURES = ROOT / "fixtures"
CASES = ROOT / "critic_cases"
AUDIT = ROOT / "results" / "render_audit.csv"

PURPOSE = {
    "landing": "the landing page of Northwind, a B2B product-analytics startup.",
    "pricing": "the pricing page of a B2B analytics product, with three plans.",
    "dashboard": "an internal operations dashboard for a delivery company.",
    "bilingual": "an Arabic-first home-services app (plumbers, electricians) with an English section.",
    "palette": "a showcase of four brand colors, each with a name and a short description.",
}

ICONS_AS_TEXT = """(() => {
  const icons = [...document.querySelectorAll('[data-fsa-icon]')];
  for (const el of icons) el.style.setProperty('font-family', 'Arial, sans-serif', 'important');
  return icons.length ? icons[0].dataset.fsaId : null; })()"""


# Text with at least six a/e/o letters to swap (so not Arabic, not a short label).
LATIN_TEXT = ('"[data-fsa-target]"', "e => (e.textContent.match(/[aeo]/g) || []).length >= 6 "
              "&& !e.closest('button,a,[role=button]')")


def mixed_fonts(seed: int) -> str:
    """Draw the letters a, e and o of one text element in Times New Roman, which is how
    text looks when a font is missing some glyphs and the browser fills them in."""
    return planted._js(LATIN_TEXT, seed, """
  for (const node of [...el.childNodes]) {
    if (node.nodeType !== 3 || !node.textContent.trim()) continue;
    const frag = document.createDocumentFragment();
    for (const part of node.textContent.split(/([aeo])/)) {
      if (/^[aeo]$/.test(part)) {
        const s = document.createElement('span');
        s.textContent = part;
        s.style.setProperty('font-family', '"Times New Roman", serif', 'important');
        frag.append(s);
      } else frag.append(part);
    }
    node.replaceWith(frag);
  }""")


DAMAGES = {
    "cut_off_text": dict(mutate=planted.clip),
    "wrapped_label": dict(mutate=planted.wrap),
    "icon_shown_as_text": dict(mutate=lambda seed: ICONS_AS_TEXT),
    "mixed_fonts": dict(mutate=mixed_fonts),
    "faked_bold": dict(mutate=None, weights=[400]),
}


def candidate_pools(seed: int) -> dict[str, list[str]]:
    """Fonts to try per page, in a seeded random order.

    Fonts whose v2 render of the page was clean in the Phase 1 audit. Few fonts cover
    Arabic, so the bilingual page draws instead from catalogue families with Arabic,
    Latin and a bold face. Every font is re-rendered and kept only if still clean.
    """
    audit = pd.read_csv(AUDIT)
    clean = audit[(audit.strategy == "v2") & (audit.viewport == "desktop")
                  & (audit.verdict == "clean")]
    pools = {page: sorted(group.font) for page, group in clean.groupby("fixture")}
    pools["bilingual"] = sorted(f.family for f in load_catalog().families
                                if f.supports("arabic") and f.supports("latin") and f.has_bold)
    rng = random.Random(seed)
    for fonts in pools.values():
        rng.shuffle(fonts)
    return pools


async def build(per_page: int, seed: int) -> list[dict]:
    cases: list[dict] = []
    async with Renderer() as renderer:
        for page, pool in sorted(candidate_pools(seed).items()):
            with page_url(str(FIXTURES / f"{page}.html")) as url:
                original = CASES / f"{page}__original.png"
                baseline = await renderer.render(url, None, screenshot=str(original))
                texts = {b["id"]: b["text"] for b in baseline.layout["blocks"]}
                kept = 0
                for font in pool:
                    if kept == per_page:
                        break
                    slug = font.lower().replace(" ", "_")
                    clean_id = f"{page}__{slug}"
                    r = await renderer.render(url, font, baseline=baseline,
                                              screenshot=str(CASES / f"{clean_id}.png"))
                    if r.issues:  # not clean on this render: try the next font
                        continue
                    i = kept
                    kept += 1
                    cases.append(_case(clean_id, page, font, None, None, r, texts))
                    for damage, how in DAMAGES.items():
                        mutate = how["mutate"](seed * 100 + i) if how["mutate"] else None
                        case_id = f"{clean_id}__{damage}"
                        r = await renderer.render(url, font, baseline=baseline, mutate_js=mutate,
                                                  weights=how.get("weights"),
                                                  screenshot=str(CASES / f"{case_id}.png"))
                        if mutate and r.mutation is None:
                            continue  # this page has no element to plant it on
                        cases.append(_case(case_id, page, font, damage, clean_id, r, texts))
            print(f"{page}: {sum(c['page'] == page for c in cases)} cases", flush=True)
    return cases


def _case(case_id, page, font, damage, twin, result, texts) -> dict:
    element = result.mutation if isinstance(result.mutation, str) else None
    return {
        "id": case_id, "page": page, "font": font, "damage": damage, "clean_twin": twin,
        "element": element, "element_text": texts.get(element, "") if element else "",
        "candidate": f"{case_id}.png", "original": f"{page}__original.png",
        "purpose": PURPOSE[page],
        "checks": [i.message for i in result.issues],
        "check_kinds": sorted({i.kind for i in result.issues}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--per-page", type=int, default=4)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()
    CASES.mkdir(exist_ok=True)
    cases = asyncio.run(build(args.per_page, args.seed))
    (CASES / "manifest.json").write_text(json.dumps(cases, indent=1, ensure_ascii=False),
                                         encoding="utf-8")
    damaged = pd.Series([c["damage"] for c in cases]).value_counts(dropna=False)
    print(f"\n{len(cases)} cases\n{damaged.to_string()}")


if __name__ == "__main__":
    main()
