import pytest

from verdict.reviews.claude_report import citations
from tests.verdict.reviews.claude_report.samples import FILES


@pytest.mark.parametrize("cited,expected", [
    (["ft_strchr.c:20"], [("ft_strchr.c", 20)]),
    (["ft_strchr.c:20,24", "Makefile:23-25"], [("ft_strchr.c", 20), ("Makefile", 23)]),
    (["./main.c:3"], [("main.c", 3)]),
    (["Makefile"], [("Makefile", None)]),
    (["ghost.c:1", "ft_strchr.c:31", "ft_strchr.c:0", "../etc/passwd:1", "/etc/passwd"], []),
    (["main.c:1", "main.c:2", "main.c:3", "main.c:4", "main.c:5", "main.c:6"], [("main.c", n) for n in range(1, 6)]),
    ("not a list", []), ([None, 5, {}], []),
])
def test_citations_must_point_at_real_files_and_lines(cited, expected):
    assert [(e.file, e.line) for e in citations(cited, FILES)] == expected
