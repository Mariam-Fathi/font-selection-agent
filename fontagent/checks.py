"""Deterministic checks: did the font really render, and did it break the layout?

Every check compares a render with the font against a baseline render of the same page
with its original fonts, so only problems the font introduced are reported. These
checks need no model and are the ground floor the critic (phase 2) builds on.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

ERROR, WARNING = "error", "warning"


@dataclass(frozen=True)
class Issue:
    kind: str
    severity: str
    message: str
    element: str | None = None  # data-fsa-id(s) of the element(s), comma-separated

    def to_dict(self) -> dict:
        return asdict(self)


def font_issues(family: str, css_status: int | None, faces: dict, coverage: dict) -> list[Issue]:
    """Problems with the font itself: it didn't load, lacks glyphs, or was faked."""
    issues: list[Issue] = []
    if css_status != 200 or not faces["loaded_faces"]:
        why = ("the font CSS could not be fetched" if css_status is None
               else f"the font CSS returned HTTP {css_status}" if css_status != 200
               else "no face loaded")
        issues.append(Issue("font_not_loaded", ERROR,
                            f"{family} never rendered ({why}); the screenshot shows a fallback font"))
        return issues
    fallbacks = coverage["fallback_elements"]
    if fallbacks:
        missing = sum(el["missing"] for el in fallbacks)
        fonts = sorted({name for el in fallbacks for name in el["fallback_fonts"]})
        issues.append(Issue(
            "glyph_fallback", WARNING,
            f"{family} doesn't cover all the text: {missing} glyphs in {len(fallbacks)} element(s) "
            f"were drawn by {', '.join(fonts) or 'another font'}, e.g. \"{fallbacks[0]['text']}\"",
            ",".join(el["id"] for el in fallbacks)))
    for kind, ids, what in (("synthetic_bold", faces["synthetic_bold"], "bold"),
                            ("synthetic_italic", faces["synthetic_italic"], "italic")):
        if ids:
            issues.append(Issue(
                kind, WARNING,
                f"{len(ids)} {what} element(s) are faked by the browser: no {what} face of "
                f"{family} is loaded", ",".join(ids)))
    return issues


def layout_issues(baseline: dict, candidate: dict, height_tolerance: float = 0.25,
                  tolerance_px: int = 2) -> list[Issue]:
    """Layout problems present with the font that weren't there before."""
    issues: list[Issue] = []
    before = {b["id"]: b for b in baseline["blocks"]}
    for block in candidate["blocks"]:
        old = before.get(block["id"])
        if old is None:
            continue
        label = f"<{block['tag']}> \"{block['text'][:40]}\""
        clipped = _grew(old, block, "clip", tolerance_px)
        spilled = _grew(old, block, "spill", tolerance_px)
        if clipped:
            issues.append(Issue("clipped_text", ERROR,
                                f"{label} is cut off by its container ({clipped}px hidden)",
                                block["id"]))
        elif spilled:
            issues.append(Issue("text_spill", WARNING,
                                f"{label} overflows its box by {spilled}px", block["id"]))
        if block["lines"] > old["lines"] and old["lines"] == 1:
            if block["control"]:
                issues.append(Issue("control_wraps", ERROR,
                                    f"{label} wraps onto {block['lines']} lines", block["id"]))
            elif block["heading"]:
                issues.append(Issue("heading_wraps", WARNING,
                                    f"{label} wraps onto {block['lines']} lines", block["id"]))
        if old["icon"] and block["family"] != old["family"]:
            issues.append(Issue("icon_font_overridden", ERROR,
                                f"icon {label} lost its icon font and renders as text",
                                block["id"]))
    if (candidate["scroll_width"] > candidate["viewport_width"]
            and baseline["scroll_width"] <= baseline["viewport_width"]):
        extra = candidate["scroll_width"] - candidate["viewport_width"]
        issues.append(Issue("horizontal_overflow", ERROR,
                            f"the page now scrolls sideways ({extra}px wider than the screen)"))
    growth = candidate["page_height"] / max(baseline["page_height"], 1) - 1
    if abs(growth) > height_tolerance:
        issues.append(Issue("page_height_change", WARNING,
                            f"the page is {growth:+.0%} taller than with its original fonts"))
    return issues


def _grew(old: dict, new: dict, kind: str, tolerance_px: int) -> int:
    """Pixels of overflow the change added on the worse axis (0 if within tolerance)."""
    added = max(new[f"{kind}_x"] - old[f"{kind}_x"], new[f"{kind}_y"] - old[f"{kind}_y"])
    return added if added > tolerance_px else 0


def glyph_coverage(family: str, per_element: dict[str, list[dict]],
                   baseline_custom: set[str], texts: dict[str, str]) -> dict:
    """Share of glyphs actually drawn with `family`, from Chrome's platform-font report.

    A glyph counts as drawn with the font when its face is a web font that is either
    named like the requested family or wasn't on the page before the change (the file's
    internal name sometimes differs from the catalogue name).
    """
    want = _norm(family)
    total = drawn = 0
    fallbacks = []
    for el_id, fonts in per_element.items():
        mine = sum(f["glyphCount"] for f in fonts if _counts_as(f, want, baseline_custom))
        count = sum(f["glyphCount"] for f in fonts)
        total += count
        drawn += mine
        if count and mine < count:
            fallbacks.append({
                "id": el_id, "text": texts.get(el_id, "")[:40], "glyphs": count,
                "missing": count - mine,
                "fallback_fonts": sorted({f["familyName"] for f in fonts if f["glyphCount"]
                                          and not _counts_as(f, want, baseline_custom)}),
            })
    return {"glyphs": total, "glyphs_in_font": drawn,
            "coverage": drawn / total if total else 0.0, "fallback_elements": fallbacks}


def _counts_as(font: dict, want: str, baseline_custom: set[str]) -> bool:
    name = _norm(font["familyName"])
    return bool(font.get("isCustomFont")) and (
        name.startswith(want) or font["familyName"] not in baseline_custom)


def _norm(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())
