from fontagent import checks


def block(id, **kw):
    base = {"id": id, "tag": "button", "text": "Buy now", "control": True, "heading": False,
            "target": True, "icon": False, "family": "Inter", "weight": 400, "lines": 1,
            "x": 0, "y": 0, "w": 100, "h": 20, "clip_x": 0, "clip_y": 0, "spill_x": 0, "spill_y": 0}
    return base | kw


def page(*blocks, scroll_width=1280, height=1000):
    return {"viewport_width": 1280, "scroll_width": scroll_width, "page_height": height,
            "blocks": list(blocks)}


def kinds(issues):
    return sorted(i.kind for i in issues)


def test_identical_layouts_report_nothing():
    p = page(block("0"), block("1", tag="p", control=False, lines=4))
    assert checks.layout_issues(p, p) == []


def test_only_problems_the_font_introduced_are_reported():
    before = page(block("0", clip_x=30), block("1"))
    after = page(block("0", clip_x=30), block("1", clip_x=25))
    issues = checks.layout_issues(before, after)
    assert kinds(issues) == ["clipped_text"]
    assert issues[0].element == "1"


def test_invisible_baseline_overflow_does_not_mask_a_real_clip():
    # Regression: a bordered button whose line-height overflows by 2px was already
    # "clipped" in the baseline, which hid real clipping found by the benchmark.
    before = page(block("0", clip_y=2))
    after = page(block("0", clip_y=2, clip_x=48))
    assert kinds(checks.layout_issues(before, after)) == ["clipped_text"]
    assert kinds(checks.layout_issues(before, page(block("0", clip_y=3)))) == []


def test_wrapping_is_an_error_for_controls_and_a_warning_for_headings():
    before = page(block("0"), block("1", tag="h1", control=False, heading=True),
                  block("2", tag="p", control=False))
    after = page(block("0", lines=2), block("1", tag="h1", control=False, heading=True, lines=2),
                 block("2", tag="p", control=False, lines=2))
    by_kind = {i.kind: i for i in checks.layout_issues(before, after)}
    assert by_kind["control_wraps"].severity == checks.ERROR
    assert by_kind["heading_wraps"].severity == checks.WARNING
    assert len(by_kind) == 2  # a paragraph gaining a line is normal


def test_icon_that_loses_its_font_is_flagged():
    before = page(block("0", icon=True, family="Material Symbols Outlined"))
    after = page(block("0", icon=True, family="Lobster"))
    assert kinds(checks.layout_issues(before, after)) == ["icon_font_overridden"]


def test_sideways_scrolling_and_height_change():
    issues = checks.layout_issues(page(), page(scroll_width=1400, height=1400))
    assert kinds(issues) == ["horizontal_overflow", "page_height_change"]


def test_glyph_coverage_separates_the_new_font_from_fallbacks():
    per_element = {
        "0": [{"familyName": "Lobster", "isCustomFont": True, "glyphCount": 7},
              {"familyName": "Times New Roman", "isCustomFont": False, "glyphCount": 12}],
        "1": [{"familyName": "Lobster", "isCustomFont": True, "glyphCount": 10}],
    }
    cov = checks.glyph_coverage("Lobster", per_element, set(), {"0": "Hello مرحبا"})
    assert cov["glyphs"] == 29 and cov["glyphs_in_font"] == 17
    assert [e["id"] for e in cov["fallback_elements"]] == ["0"]
    assert cov["fallback_elements"][0]["fallback_fonts"] == ["Times New Roman"]


def test_fallback_to_the_pages_own_web_font_is_not_credited_to_the_candidate():
    per_element = {"0": [{"familyName": "Cairo", "isCustomFont": True, "glyphCount": 5},
                         {"familyName": "Lobster", "isCustomFont": True, "glyphCount": 5}]}
    cov = checks.glyph_coverage("Lobster", per_element, {"Cairo"}, {})
    assert cov["coverage"] == 0.5


def test_font_that_never_loaded_is_an_error():
    faces = {"loaded_faces": [], "synthetic_bold": [], "synthetic_italic": []}
    issues = checks.font_issues("Nope", 400, faces, {"fallback_elements": []})
    assert kinds(issues) == ["font_not_loaded"]
    assert "HTTP 400" in issues[0].message


def test_faked_bold_lists_every_affected_element():
    faces = {"loaded_faces": ["normal 400"], "synthetic_bold": ["3", "8"], "synthetic_italic": []}
    issues = checks.font_issues("Lobster", 200, faces, {"fallback_elements": []})
    assert kinds(issues) == ["synthetic_bold"]
    assert issues[0].element == "3,8"
