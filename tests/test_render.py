"""Browser tests. `browser` tests run offline; `network` tests also need Google Fonts."""

import hashlib

import pytest

from benchmark import planted
from fontagent.render import Renderer, page_url
from tools.font_screenshot import take_font_screenshots

pytestmark = pytest.mark.browser


@pytest.fixture
async def renderer():
    async with Renderer() as r:
        yield r


async def test_page_compared_with_itself_has_no_issues(renderer, simple_page):
    with page_url(str(simple_page)) as url:
        baseline = await renderer.render(url, None)
        again = await renderer.render(url, None, baseline=baseline)
    assert baseline.layout["blocks"]
    assert again.issues == []


@pytest.mark.parametrize("mutation, expected", [
    (planted.clip, "clipped_text"),
    (planted.wrap, "control_wraps"),
    (planted.overflow, "horizontal_overflow"),
])
async def test_planted_layout_flaws_are_found(renderer, simple_page, mutation, expected):
    with page_url(str(simple_page)) as url:
        baseline = await renderer.render(url, None)
        result = await renderer.render(url, None, baseline=baseline, mutate_js=mutation(0))
    assert expected in [i.kind for i in result.issues]


async def test_icon_fonts_are_never_targeted(renderer, simple_page):
    with page_url(str(simple_page)) as url:
        baseline = await renderer.render(url, None)
    icon = next(b for b in baseline.layout["blocks"] if b["text"] == "search")
    assert icon["icon"] and not icon["target"]


def test_non_html_file_without_url_is_rejected(tmp_path):
    component = tmp_path / "Hero.tsx"
    component.write_text("export default () => <h1>Hi</h1>")
    with pytest.raises(ValueError, match="dev server"):
        with page_url(str(component)):
            pass


async def test_tool_reports_unknown_fonts_without_rendering_them(simple_page):
    result = await take_font_screenshots(["Fredoka One"], file_path=str(simple_page))
    assert result["status"] == "success"
    assert result["results"] == []
    assert "Fredoka" in result["not_found"]["Fredoka One"]["did_you_mean"]


@pytest.mark.network
async def test_real_font_renders_and_original_file_is_untouched(simple_page):
    # The page has a link holding an icon: its icon glyph must not count as a fallback.
    before = hashlib.sha256(simple_page.read_bytes()).hexdigest()
    result = await take_font_screenshots(["Inter"], file_path=str(simple_page))
    assert hashlib.sha256(simple_page.read_bytes()).hexdigest() == before
    inter = result["results"][0]
    assert inter["rendered"] and inter["glyph_coverage"] == 1.0


@pytest.mark.network
async def test_missing_font_and_missing_glyphs_are_caught(renderer, simple_page):
    with page_url(str(simple_page)) as url:
        baseline = await renderer.render(url, None)
        missing = await renderer.render(url, "Planted Missing Font", baseline=baseline)
        arabic = await renderer.render(url, "Lobster", baseline=baseline,
                                       mutate_js=planted.arabic(0))
    assert "font_not_loaded" in [i.kind for i in missing.issues]
    assert "glyph_fallback" in [i.kind for i in arabic.issues]
    assert arabic.coverage["coverage"] < 1


@pytest.mark.network
async def test_v1_pipeline_fakes_bold_and_v2_does_not(renderer, simple_page):
    with page_url(str(simple_page)) as url:
        baseline = await renderer.render(url, None)
        v1 = await renderer.render(url, "Playfair Display", strategy="v1", baseline=baseline)
        v2 = await renderer.render(url, "Playfair Display", baseline=baseline)
    assert "synthetic_bold" in [i.kind for i in v1.issues]
    assert "synthetic_bold" not in [i.kind for i in v2.issues]
