import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PAGES = Path(__file__).parent / "pages"


@pytest.fixture
def simple_page() -> Path:
    return PAGES / "simple.html"
