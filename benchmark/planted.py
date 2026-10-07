"""Plant known flaws in real pages and check that the detector finds every one.

The same idea as checking an A/B analysis against effects planted in a simulator: each
trial breaks a page in a known way, at a known element, and the detector passes only
if it reports that problem at that element. Control trials change nothing harmful and
must report nothing, which measures false alarms.

    python -m benchmark.planted --seeds 10
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path

from fontagent.catalog import load_catalog
from fontagent.render import Renderer, RenderResult, page_url

FIXTURES = Path(__file__).parent / "fixtures"
RESULTS = Path(__file__).parent / "results"

# Each mutation picks one eligible element using the trial's seed, changes it, and
# returns its data-fsa-id so the check can be tied to that element.
PICK = """
  const pool = [...document.querySelectorAll(SELECTOR)].filter(FILTER);
  if (!pool.length) return null;
  const el = pool[SEED % pool.length];
"""
CONTROL_WITH_SPACE = ('"[data-fsa-target]"', "e => e.closest('button,a,label,th,td,[role=button]') "
                      "&& e.textContent.trim().includes(' ') && e.getBoundingClientRect().width > 40")
CONTROL_ANY = ('"[data-fsa-target]"', "e => e.closest('button,a,label,th,td,[role=button]') "
               "&& e.getBoundingClientRect().width > 40")
TEXT_TARGET = ('"[data-fsa-target]"', "e => e.textContent.trim().length > 8")


def _js(pick: tuple[str, str], seed: int, body: str) -> str:
    selector, keep = pick
    head = PICK.replace("SELECTOR", selector).replace("FILTER", keep).replace("SEED", str(seed))
    return f"(() => {{ {head} {body} return el.dataset.fsaId; }})()"


# Width of the element's own text, so a planted box is narrower than the text itself
# (halving the element's box isn't enough when padding absorbs the difference).
TEXT_WIDTH = """
  const range = document.createRange();
  let textW = 0;
  for (const n of el.childNodes) if (n.nodeType === 3 && n.textContent.trim()) {
    range.selectNodeContents(n); textW += range.getBoundingClientRect().width; }
"""


def clip(seed: int) -> str:
    return _js(CONTROL_ANY, seed, TEXT_WIDTH + """
  Object.assign(el.style, {display: 'inline-block', boxSizing: 'content-box', padding: '0',
                           width: (textW * 0.5) + 'px', whiteSpace: 'nowrap', overflow: 'hidden',
                           verticalAlign: 'top'});""")


def wrap(seed: int) -> str:
    return _js(CONTROL_WITH_SPACE, seed, TEXT_WIDTH + """
  Object.assign(el.style, {display: 'inline-block', boxSizing: 'content-box', padding: '0',
                           width: (textW * 0.45) + 'px', whiteSpace: 'normal', height: 'auto',
                           lineHeight: 'normal', overflow: 'visible'});""")


def widen(seed: int) -> str:  # benign control: more room never breaks anything
    return _js(CONTROL_ANY, seed, """
  const w = el.getBoundingClientRect().width;
  Object.assign(el.style, {display: 'inline-block', minWidth: (w + 8) + 'px'});""")


def overflow(seed: int) -> str:
    # Absolutely positioned, so a flex or grid parent can't shrink it away, and anchored
    # at the inline start: in a right-to-left page, overflow past the right edge can't
    # be scrolled to, so it isn't sideways scrolling.
    return """(() => { const d = document.createElement('div');
  const side = getComputedStyle(document.documentElement).direction === 'rtl' ? 'right' : 'left';
  d.style.cssText = `position:absolute;top:0;${side}:0;width:140vw;height:1px`;
  document.body.appendChild(d); return null; })()"""


def arabic(seed: int) -> str:
    return _js(TEXT_TARGET, seed, "el.append(' مرحبا بالعالم');")


def bold(seed: int) -> str:
    return _js(TEXT_TARGET, seed, "el.style.fontWeight = '700';")


@dataclass
class Trial:
    kind: str
    planted: bool  # True: a flaw was planted and must be found. False: a control.
    expects: str | None  # the issue kind that counts as "found"
    mutate: object = None
    font: str | None = None
    weights: list[int] | None = None


def trials(seed: int) -> list[Trial]:
    rng = random.Random(seed)
    catalog = load_catalog()
    popular = catalog.families[:300]
    latin_only = [f for f in popular if not f.supports("arabic")]
    with_arabic = [f for f in catalog.families if f.supports("arabic") and f.supports("latin")]
    two_weights = [f for f in popular if 400 in f.weights and 700 in f.weights]
    return [
        Trial("clipped_text", True, "clipped_text", clip(seed)),
        Trial("control_wraps", True, "control_wraps", wrap(seed)),
        Trial("horizontal_overflow", True, "horizontal_overflow", overflow(seed)),
        Trial("font_not_loaded", True, "font_not_loaded", None, f"Planted Missing Font {seed}"),
        Trial("glyph_fallback", True, "glyph_fallback", arabic(seed), rng.choice(latin_only).family),
        Trial("synthetic_bold", True, "synthetic_bold", bold(seed), rng.choice(two_weights).family, [400]),
        Trial("control: unchanged page", False, None),
        Trial("control: wider element", False, None, widen(seed)),
        Trial("control: Arabic-capable font", False, "glyph_fallback", arabic(seed),
              rng.choice(with_arabic).family),
        Trial("control: bold face loaded", False, "synthetic_bold", bold(seed),
              rng.choice(two_weights).family),
    ]


def judge(trial: Trial, result: RenderResult) -> tuple[bool, list[str]]:
    """Did the detector flag the planted problem (at the planted element, if there is one)?"""
    kinds = [i.kind for i in result.issues]
    if trial.planted:
        hits = [i for i in result.issues if i.kind == trial.expects and (
            result.mutation is None or result.mutation in (i.element or "").split(","))]
        return bool(hits), kinds
    if trial.expects:  # a targeted control: that one issue must not appear
        return trial.expects not in kinds, kinds
    return not result.issues, kinds  # an untargeted control: nothing at all may appear


async def run(seeds: range, viewport: str) -> list[dict]:
    rows = []
    async with Renderer(viewport=viewport) as renderer:
        for fixture in sorted(FIXTURES.glob("*.html")):
            with page_url(str(fixture)) as url:
                baseline = await renderer.render(url, None)
                for seed in seeds:
                    for trial in trials(seed):
                        result = await renderer.render(
                            url, trial.font, baseline=baseline, mutate_js=trial.mutate,
                            weights=trial.weights)
                        if trial.mutate and "fsaId" in trial.mutate and result.mutation is None:
                            continue  # no eligible element on this page
                        passed, kinds = judge(trial, result)
                        rows.append({"fixture": fixture.stem, "seed": seed, "trial": trial.kind,
                                     "planted": trial.planted, "font": trial.font or "",
                                     "element": result.mutation or "", "passed": passed,
                                     "issues": ";".join(sorted(set(kinds)))})
                print(f"{fixture.stem}: {sum(r['fixture'] == fixture.stem for r in rows)} trials", flush=True)
    return rows


def summarize(rows: list[dict]) -> list[dict]:
    out = []
    for kind in dict.fromkeys(r["trial"] for r in rows):
        group = [r for r in rows if r["trial"] == kind]
        passed = sum(r["passed"] for r in group)
        out.append({"trial": kind, "planted": group[0]["planted"], "n": len(group),
                    "passed": passed, "rate": round(passed / len(group), 4)})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--first-seed", type=int, default=0,
                        help="start here for a held-out run, e.g. 10 for seeds 10-19")
    parser.add_argument("--name", default="planted", help="prefix for the output files")
    parser.add_argument("--viewport", default="desktop")
    args = parser.parse_args()
    rows = asyncio.run(run(range(args.first_seed, args.first_seed + args.seeds), args.viewport))
    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / f"{args.name}.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = summarize(rows)
    (RESULTS / f"{args.name}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n{'trial':32} {'n':>4} {'passed':>7} {'rate':>7}")
    for s in summary:
        label = ("found " if s["planted"] else "clean ") + s["trial"]
        print(f"{label:32} {s['n']:>4} {s['passed']:>7} {s['rate']:>7.1%}")


if __name__ == "__main__":
    main()
