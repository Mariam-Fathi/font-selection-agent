import pytest

from fontagent.catalog import load_catalog, normalize_category


def test_snapshot_has_the_full_catalogue():
    catalog = load_catalog()
    assert len(catalog) > 1500
    assert catalog.get("inter").family == "Inter"  # lookups ignore case


def test_renamed_fonts_from_the_v1_list_get_suggestions():
    catalog = load_catalog()
    assert catalog.get("Fredoka One") is None
    assert "Fredoka" in catalog.suggest("Fredoka One")
    assert "Source Serif 4" in catalog.suggest("Source Serif Pro")


def test_search_filters_combine_and_sort_by_popularity():
    hits = load_catalog().search(category="serif", subset="arabic", needs_bold=True, limit=50)
    assert hits
    assert all(f.category == "serif" and f.supports("arabic") and f.has_bold for f in hits)
    assert [f.popularity for f in hits] == sorted(f.popularity for f in hits)


@pytest.mark.parametrize("raw, expected", [("Sans Serif", "sans-serif"), ("script", "handwriting"),
                                           ("mono", "monospace")])
def test_category_aliases(raw, expected):
    assert normalize_category(raw) == expected


def test_unknown_category_is_an_error():
    with pytest.raises(ValueError):
        normalize_category("gothic")


def test_css_url_requests_only_faces_that_exist():
    catalog = load_catalog()
    lobster = catalog.get("Lobster")  # a single 400 face
    assert lobster.css_url({400, 700}).endswith("family=Lobster&display=block")
    inter = catalog.get("Inter")
    assert "wght@400;700" in inter.css_url({400, 700})
    assert "ital,wght@0,400;1,400" in inter.css_url({400}, italic=True)


def test_match_weights_picks_the_nearest_face():
    playfair = load_catalog().get("Playfair Display")  # 400 to 900
    assert playfair.match_weights({300, 650}) == [400, 600]


def test_italic_only_family_requests_its_italic_face():
    # Regression: the audit found Molle never loaded because only upright faces were asked for.
    molle = load_catalog().get("Molle")
    assert not molle.weights and molle.italic_weights
    assert "ital,wght@1,400" in molle.css_url({400, 700})
