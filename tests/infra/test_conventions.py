"""The structure rules of the sources, the same ones the C projects in projects/ follow (scripts/conventions/check.py):
no file over 250 lines, no function over 40, no folder with a single module, no folder that holds modules and folders."""

import importlib.util

from tests.paths import SCRIPTS, SRC

spec = importlib.util.spec_from_file_location("conventions", SCRIPTS / "conventions" / "check.py")
conventions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conventions)


def test_the_sources_follow_the_structure_rules():
    problems = conventions.check(SRC)
    assert not problems, "\n" + "\n".join(problems)


def test_the_checker_itself_sees_a_broken_rule(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "only.py").write_text("x = 1\n")
    (tmp_path / "big").mkdir()
    (tmp_path / "big" / "a.py").write_text("\n".join(f"v{i} = {i}" for i in range(300)) + "\n")
    (tmp_path / "big" / "b.py").write_text("def f():\n" + "".join(f"    x{i} = {i}\n" for i in range(45)))
    (tmp_path / "mixed").mkdir()
    (tmp_path / "mixed" / "m1.py").write_text("a = 1\n")
    (tmp_path / "mixed" / "m2.py").write_text("b = 2\n")
    (tmp_path / "mixed" / "sub").mkdir()
    (tmp_path / "mixed" / "sub" / "s1.py").write_text("c = 3\n")
    (tmp_path / "mixed" / "sub" / "s2.py").write_text("d = 4\n")
    problems = "\n".join(conventions.check(tmp_path))
    assert "pkg" in problems and "single module" in problems
    assert "a.py: 301 lines" in problems or "a.py: 300 lines" in problems
    assert "f: 46 lines" in problems
    assert "mixed" in problems and "holds modules" in problems
