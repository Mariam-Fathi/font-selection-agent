"""Render a page with a candidate font, verify what actually rendered, and measure it.

The v1 tool rewrote the user's source file, slept for fixed times and assumed the font
appeared. This renderer never touches the user's files: it loads the page in Chromium,
applies the font in the page only, waits for the exact faces it needs, then asks
Chrome which font drew each glyph and compares the layout against the original page.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, quote_plus

from playwright.async_api import Browser, Page, async_playwright
from playwright.async_api import Error as PlaywrightError

from . import checks
from .catalog import load_catalog
from .checks import Issue

VIEWPORTS = {"desktop": (1280, 800), "mobile": (390, 844)}
PAGE_JS = (Path(__file__).parent / "page.js").read_text(encoding="utf-8")
MAX_ELEMENTS = 300  # cap on elements inspected per render, to bound CDP calls


@dataclass
class RenderResult:
    font: str | None  # None for the baseline (the page's own fonts)
    strategy: str
    viewport: str
    css_url: str | None = None
    css_status: int | None = None
    loaded_faces: list[str] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    layout: dict = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    screenshot: str | None = None
    seconds: float = 0.0
    custom_fonts: set[str] = field(default_factory=set)  # web fonts drawing text
    mutation: object = None  # what a planted-flaw mutation reported, if one ran

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == checks.ERROR]

    def summary(self) -> dict:
        """A compact, JSON-safe view for the agent and for benchmark rows."""
        return {
            "font": self.font,
            "strategy": self.strategy,
            "viewport": self.viewport,
            "screenshot": self.screenshot,
            "rendered": self.css_status == 200 and bool(self.loaded_faces),
            "glyph_coverage": round(self.coverage.get("coverage", 0.0), 4),
            "verdict": "broken" if self.errors else ("warnings" if self.issues else "clean"),
            "issues": [i.to_dict() for i in self.issues],
        }


@contextlib.contextmanager
def serve_directory(directory: Path) -> Iterator[str]:
    """Serve a folder on a free localhost port for the duration of the block."""
    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


@contextlib.contextmanager
def page_url(file_path: str | None = None, url: str | None = None) -> Iterator[str]:
    """The URL to render: a running app's URL, or a local HTML file served on the fly."""
    if url:
        yield url
        return
    if not file_path:
        raise ValueError("Give either a file_path to an HTML file or the url of a running app")
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"No file at {path}")
    if path.suffix.lower() not in {".html", ".htm"}:
        raise ValueError(f"{path.suffix} files need a running dev server: pass its url instead")
    with serve_directory(path.parent) as base:
        yield f"{base}/{quote(path.name)}"


class Renderer:
    """One headless Chromium, many isolated renders (a fresh page per render)."""

    def __init__(self, viewport: str = "desktop", timeout_ms: int = 20_000):
        self.viewport = viewport
        self.timeout_ms = timeout_ms
        self._pw = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> Renderer:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def compare(self, url: str, fonts: list[str], *, scope: str = "all",
                      strategy: str = "v2", screenshot_dir: Path | None = None
                      ) -> tuple[RenderResult, list[RenderResult]]:
        """Render the page as it is, then once per font, each checked against the original."""
        shot = (lambda name: str(screenshot_dir / f"{name}.png")) if screenshot_dir else (lambda _: None)
        baseline = await self.render(url, None, scope=scope, screenshot=shot("_original"))
        results = []
        for font in fonts:
            slug = font.lower().replace(" ", "_")
            results.append(await self.render(url, font, scope=scope, strategy=strategy,
                                             baseline=baseline, screenshot=shot(slug)))
        return baseline, results

    async def render(self, url: str, font: str | None, *, scope: str = "all",
                     strategy: str = "v2", baseline: RenderResult | None = None,
                     screenshot: str | None = None, mutate_js: str | None = None,
                     weights: list[int] | None = None) -> RenderResult:
        """Render `url` with `font` applied (or as-is when font is None).

        strategy "v2" is this renderer; "v1" reproduces the original tool's approach
        (a single 400 face, forced onto every element) so the two can be compared.
        `mutate_js` and `weights` exist for the planted-flaw benchmark.
        """
        started = time.perf_counter()
        width, height = VIEWPORTS[self.viewport]
        page = await self._browser.new_page(viewport={"width": width, "height": height})
        result = RenderResult(font=font, strategy=strategy, viewport=self.viewport)
        try:
            await page.goto(url, wait_until="load", timeout=self.timeout_ms)
            await page.evaluate("document.fonts.ready.then(() => true)")
            await page.evaluate(PAGE_JS)
            prep = await page.evaluate("o => window.__fsa.prepare(o)", {"scope": scope})
            if mutate_js:
                result.mutation = await page.evaluate(mutate_js)
            if font:
                await self._apply_font(page, result, font, strategy, prep, weights)
            result.layout = await page.evaluate("() => window.__fsa.measure()")
            texts = {b["id"]: b["text"] for b in result.layout["blocks"]}
            fonts_by_el = await _platform_fonts(page)
            result.custom_fonts = {f["familyName"] for fs in fonts_by_el.values()
                                   for f in fs if f.get("isCustomFont")}
            if font:
                known = baseline.custom_fonts if baseline else set()
                targets = {b["id"] for b in result.layout["blocks"] if b["target"]}
                result.coverage = checks.glyph_coverage(
                    font, {k: v for k, v in fonts_by_el.items() if k in targets}, known, texts)
                faces = await page.evaluate("o => window.__fsa.faces(o)", {"family": font})
                result.loaded_faces = faces["loaded_faces"]
                result.issues = checks.font_issues(font, result.css_status, faces, result.coverage)
            if baseline:
                result.issues += checks.layout_issues(baseline.layout, result.layout)
            if screenshot:
                Path(screenshot).parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=screenshot, full_page=True)
                result.screenshot = screenshot
        finally:
            await page.close()
            result.seconds = round(time.perf_counter() - started, 2)
        return result

    async def _apply_font(self, page: Page, result: RenderResult, font: str, strategy: str,
                          prep: dict, weights: list[int] | None) -> None:
        family = load_catalog().get(font)
        if strategy == "v1":
            result.css_url = (f"https://fonts.googleapis.com/css2?family={quote_plus(font)}"
                              ":wght@400&display=swap")
        elif family:
            needed = set(weights or prep["weights"])
            result.css_url = family.css_url(needed, italic=prep["italic"])
        else:  # not in the catalogue: ask anyway, and let the check report the failure
            result.css_url = f"https://fonts.googleapis.com/css2?family={quote_plus(font)}&display=block"
        try:
            response = await page.request.get(result.css_url, timeout=self.timeout_ms)
            result.css_status = response.status
        except PlaywrightError:  # offline, DNS failure: reported as font_not_loaded
            result.css_status = None
        if result.css_status == 200:
            await page.add_style_tag(url=result.css_url)
        if strategy == "v1":
            await page.add_style_tag(
                content=f'* {{ font-family: "{font}", sans-serif !important; }}')
        else:
            await page.evaluate("o => window.__fsa.apply(o)", {"family": font})
        await page.evaluate("o => window.__fsa.waitForFonts(o)", {
            "family": font, "weights": weights or prep["weights"], "italic": prep["italic"],
            "sample": prep["sample"], "timeoutMs": self.timeout_ms // 2})


async def _platform_fonts(page: Page) -> dict[str, list[dict]]:
    """For each tagged element, the fonts Chrome used for its own text, with glyph counts.

    Chrome's report for an element covers its whole subtree, so a link holding an icon
    would count the icon's glyphs as its own. Each element's report therefore has the
    reports of its nearest tagged descendants subtracted.
    """
    tree = await page.evaluate("""() => [...document.querySelectorAll('[data-fsa-id]')].map(e => [
        e.dataset.fsaId,
        [...e.querySelectorAll('[data-fsa-id]')]
          .filter(d => d.parentElement.closest('[data-fsa-id]') === e).map(d => d.dataset.fsaId)])""")
    cdp = await page.context.new_cdp_session(page)
    try:
        await cdp.send("DOM.enable")
        await cdp.send("CSS.enable")
        root = (await cdp.send("DOM.getDocument", {"depth": -1}))["root"]["nodeId"]
        nodes = (await cdp.send("DOM.querySelectorAll",
                                {"nodeId": root, "selector": "[data-fsa-id]"}))["nodeIds"]
        raw = {}
        for (el_id, _), node in list(zip(tree, nodes, strict=True))[:MAX_ELEMENTS]:
            raw[el_id] = (await cdp.send("CSS.getPlatformFontsForNode", {"nodeId": node}))["fonts"]
    finally:
        await cdp.detach()
    own = {}
    for el_id, children in tree:
        if el_id not in raw:
            continue
        counts = {f["familyName"]: dict(f) for f in raw[el_id]}
        for child in children:
            for f in raw.get(child, []):
                if f["familyName"] in counts:
                    counts[f["familyName"]]["glyphCount"] -= f["glyphCount"]
        own[el_id] = [f for f in counts.values() if f["glyphCount"] > 0]
    return own
