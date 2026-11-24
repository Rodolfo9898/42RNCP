import pytest

from tests.conftest import NORM_PAGES
from tests.paths import SAMPLES as LIBRARY
from verdict.subjects.pdf import read_pages
from verdict.subjects.spec import parse_norm


def test_norm_keeps_only_what_norminette_cannot_check():
    spec = parse_norm("en.norm.pdf", NORM_PAGES)
    assert spec.lang == "c"
    assert [r.kind for r in spec.rules].count("norm") == 1
    manual = [r.text for r in spec.rules if r.kind == "manual"]
    assert manual == ["Your comments should be in English, and useful.", "Inclusion of unused headers is forbidden."]
    assert all(r.sources[0].pdf == "en.norm.pdf" for r in spec.rules)


@pytest.mark.skipif(not (LIBRARY / "en.norm.pdf").exists(), reason="the Norm is not present")
def test_real_norm_lists_the_starred_rules():
    spec = parse_norm("en.norm.pdf", read_pages(LIBRARY / "en.norm.pdf"))
    manual = [r.text for r in spec.rules if r.kind == "manual"]
    assert len(manual) == 9
    assert any("unused headers" in t for t in manual) and any("42 header" in t for t in manual)
