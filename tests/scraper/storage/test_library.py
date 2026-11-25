"""src/scraper/storage: what the library says about the projects (missing, to visit, how a path is shown) and one read of the folder."""
from __future__ import annotations

from pathlib import Path

from scraper.plan.catalog import Project
from scraper.plan.target import Target
from scraper.storage.library import Library
from scraper.storage.reorganize import Reorganizer
from tests.scraper.test_scraper import PDF


def targets(*slugs: str, track: str = "common-core") -> list[Target]:
    return [Target(track, Project(i, slug, slug)) for i, slug in enumerate(slugs, 1)]


def library_with(tmp_path, *files: str) -> Library:
    for rel in files:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(PDF)
    return Library(tmp_path / "samples", tmp_path / "artifacts")


def test_the_missing_projects_are_the_ones_without_a_pdf_whatever_its_spelling_or_folder(tmp_path):
    library = library_with(tmp_path, "samples/common-core/Libft.pdf", "samples/rncp/kfs_1.pdf")
    assert [t.stem for t in library.missing(targets("libft", "kfs-1", "pipex"))] == ["pipex"]
    assert library.missing([]) == []


def test_a_page_is_visited_when_the_pdf_is_missing_or_the_artifacts_were_not_read_yet(tmp_path):
    library = library_with(tmp_path, "samples/common-core/libft.pdf", "samples/common-core/pipex.pdf")
    library.mark_checked("libft")
    wanted = targets("libft", "pipex", "so_long")
    assert [t.stem for t in library.visits(wanted, with_artifacts=True)] == ["pipex", "so_long"]
    assert [t.stem for t in library.visits(wanted, with_artifacts=False)] == ["so_long"]
    assert [t.stem for t in library.visits(wanted, with_artifacts=False, force=True)] == ["libft", "pipex", "so_long"]


def test_a_path_is_shown_from_the_folder_that_holds_the_samples(tmp_path):
    library = Library(tmp_path / "samples", tmp_path / "artifacts")
    assert library.shown(tmp_path / "samples/common-core/libft.pdf") == "samples/common-core/libft.pdf"
    assert library.shown(tmp_path / "artifacts/cpp-modules/cpp00") == "artifacts/cpp-modules/cpp00"
    assert library.shown(tmp_path / "elsewhere/x.pdf") == "elsewhere/x.pdf"             # (anywhere below the folder that holds them)
    assert library.shown(Path("/not/below/the/library/x.pdf")) == "x.pdf"


def test_samples_and_artifacts_in_different_places_are_each_shown_from_their_own_parent(tmp_path):
    library = Library(tmp_path / "a" / "samples", tmp_path / "b" / "artifacts")
    assert library.shown(tmp_path / "a/samples/rncp/x.pdf") == "samples/rncp/x.pdf" and library.shown(tmp_path / "b/artifacts/x") == "artifacts/x"


def test_reorganizing_reads_the_folder_once_for_all_the_projects(tmp_path):
    reads = []

    class Counting(Library):
        def pdfs(self):
            reads.append(1)
            return super().pdfs()

    library_with(tmp_path, "samples/common-core/cpp00.pdf")
    counting = Counting(tmp_path / "samples", tmp_path / "artifacts")
    moves = Reorganizer(counting).moves([Target("common-core", Project(i, f"cpp-module-0{i}", f"cpp-module-0{i}"), group="cpp-modules")
                                         for i in range(10)])
    assert len(reads) == 1 and [m.destination.name for m in moves] == ["cpp00.pdf"]
