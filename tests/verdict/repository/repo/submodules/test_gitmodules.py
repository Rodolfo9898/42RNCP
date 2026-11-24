from verdict.repository import repo


def test_submodule_folders_are_read_as_text_and_empty_ones_are_found(tmp_path):
    (tmp_path / ".gitmodules").write_text('[submodule "a"]\n\tpath = libs/a\n\turl = x\n[submodule "b"]\n\tpath = libs/b\n[submodule "c"]\n\tpath = ../escape\n[submodule "d"]\n\tpath = has space/d\n')
    (tmp_path / "libs" / "a").mkdir(parents=True)
    (tmp_path / "libs" / "b").mkdir()
    (tmp_path / "libs" / "b" / "full.c").write_text("x")
    assert repo.submodule_paths(tmp_path) == ["libs/a", "libs/b"]
    assert repo.empty_submodules(tmp_path) == ["libs/a"]
    assert repo.submodule_paths(tmp_path / "nowhere") == [] and repo.empty_submodules(tmp_path / "nowhere") == []


def test_a_submodule_that_was_never_created_counts_as_empty(tmp_path):
    (tmp_path / ".gitmodules").write_text('[submodule "a"]\n\tpath = libs/a\n')
    assert repo.empty_submodules(tmp_path) == ["libs/a"]
