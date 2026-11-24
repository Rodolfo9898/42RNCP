"""A series has a folder of its own, in samples/<track>/ and in artifacts/ (like cpp-modules/ in the projects folder)."""
from __future__ import annotations

from pathlib import Path

from scraper.cli.reorganize import ReorganizeCommand
from scraper.plan.catalog import Catalog, Project
from scraper.plan.groups import GroupingRule, Placement
from scraper.plan.layout import LayoutPlanner
from scraper.plan.target import Target
from scraper.plan.tracks import TRACKS, build_plan
from scraper.core.config import DATA
from scraper.storage.library import Library
from scraper.storage.reorganize import Reorganizer
from tests.scraper.test_scraper import PDF, Buffer, FakeSite, run_scrape


def project(slug: str, pid: int, *children: Project) -> Project:
    return Project(pid, slug, slug, tuple(children))


def targets(track: str, *slugs: str) -> list[Target]:
    return [Target(track, project(slug, i)) for i, slug in enumerate(slugs, 1)]


def folders(placed: list[Target]) -> dict[str, str]:
    return {t.stem: t.group for t in placed}


# ---------------------------------------------------------------------------------------------------- the rules


def test_numbered_projects_go_in_the_folder_of_their_series_and_a_lone_one_stays_alone():
    placed = LayoutPlanner().place(targets("common-core", "cpp-module-00", "cpp-module-01", "cpp-module-09", "libft", "little-penguin-1"))
    assert folders(placed) == {"cpp00": "cpp-modules", "cpp01": "cpp-modules", "cpp09": "cpp-modules", "libft": "", "little-penguin-1": ""}


def test_the_suffix_x_counts_like_a_number():
    placed = LayoutPlanner().place(targets("rncp", "42cursus-kfs-1", "42cursus-kfs-2", "42cursus-kfs-x"))
    assert set(folders(placed).values()) == {"kfs"} and {t.stem for t in placed} == {"kfs1", "kfs2", "kfsx"}


def test_a_series_needs_two_projects_in_its_own_track():
    placed = LayoutPlanner().place([*targets("rncp", "foo-1"), *targets("common-core", "foo-2")])
    assert folders(placed) == {"foo-1": "", "foo-2": ""}                          # one in each track: nothing to fold
    assert folders(LayoutPlanner(min_group=3).place(targets("rncp", "foo-1", "foo-2"))) == {"foo-1": "", "foo-2": ""}


def test_the_projects_of_a_piscine_and_the_piscine_itself_share_the_folder_of_the_piscine():
    day0, day1 = project("42cursus-piscine-php-symfony-day-00", 11), project("42cursus-piscine-php-symfony-day-01", 12)
    piscine = project("42cursus-piscine-php-symfony", 10, day0, day1)
    placed = LayoutPlanner().place([Target("rncp", piscine), Target("rncp", day0, piscine), Target("rncp", day1, piscine)])
    assert folders(placed) == {"piscine-php-symfony": "piscine-php-symfony", "piscine-php-symfony-day-00": "piscine-php-symfony",
                               "piscine-php-symfony-day-01": "piscine-php-symfony"}


def test_a_piscine_with_a_single_project_still_has_its_folder():
    only = project("django-0-initiation", 2)
    placed = LayoutPlanner().place([Target("rncp", project("piscine-django", 1, only)), Target("rncp", only, project("piscine-django", 1))])
    assert {t.group for t in placed} == {"piscine-django"}


def test_the_order_of_the_input_does_not_change_the_layout():
    slugs = ["cpp-module-00", "cpp-module-01", "libft", "kfs-1", "kfs-2"]
    forward = folders(LayoutPlanner().place(targets("common-core", *slugs)))
    assert forward == folders(LayoutPlanner().place(targets("common-core", *reversed(slugs))))


def test_a_folder_never_shares_its_name_with_a_project_that_has_none():
    placed = LayoutPlanner().place(targets("rncp", "kfs", "kfs-1", "kfs-2"))
    assert folders(placed)["kfs"] == "" and folders(placed)["kfs1"] == "kfs-series" == folders(placed)["kfs2"]


def test_a_new_kind_of_series_is_one_new_class():
    class RomanRule(GroupingRule):
        name = "roman"

        def match(self, target, heads):
            stem, _, numeral = target.slug.rpartition("-")
            return Placement(self.name, stem) if stem and numeral in ("i", "ii", "iii") else None

    placed = LayoutPlanner(rules=[RomanRule()]).place(targets("rncp", "part-time-i", "part-time-ii"))
    assert set(folders(placed).values()) == {"part-time"}


def test_the_folders_hold_the_pdf_and_its_artifacts(tmp_path):
    cpp = Target("common-core", project("cpp-module-03", 1), group="cpp-modules")
    plain = Target("rncp", project("42cursus-darkly", 2))
    library = Library(tmp_path / "samples", tmp_path / "artifacts")
    assert library.pdf_path(cpp) == tmp_path / "samples" / "common-core" / "cpp-modules" / "cpp03.pdf"
    assert library.artifact_dir(cpp) == tmp_path / "artifacts" / "cpp-modules" / "cpp03"
    assert library.pdf_path(plain) == tmp_path / "samples" / "rncp" / "darkly.pdf" and library.artifact_dir(plain) == tmp_path / "artifacts" / "darkly"


def test_the_shipped_plan_has_the_series_of_the_library():
    plan = build_plan(Catalog.load(DATA / "projects_21.json"), DATA)
    groups = {(t.track, t.group) for t in plan.targets if t.group}
    assert {("common-core", "cpp-modules"), ("rncp", "kfs"), ("rncp", "piscine-django"), ("rncp", "cybersecurity")} <= groups
    for track, group in groups:
        names = [t.stem for t in plan.of(track) if t.group == group]
        assert len(names) == len(set(names)) >= 2 or group.startswith("piscine"), (track, group, names)
    assert len({t.stem for t in plan.targets}) == len(plan.targets)               # no two projects share a file name


# ------------------------------------------------------------------------------------------------------ a run


def test_a_run_files_the_pdf_and_the_artifacts_in_the_folder_of_the_series(tmp_path):
    site = FakeSite()
    site.add_project("cpp-module-03", "CPP Module 03", artifacts=("ex00.tgz",))
    cpp = Target("common-core", project("cpp-module-03", 1), group="cpp-modules")
    _, _, library = run_scrape(tmp_path, site, [cpp])
    assert (tmp_path / "samples" / "common-core" / "cpp-modules" / "cpp03.pdf").read_bytes() == PDF
    assert (tmp_path / "artifacts" / "cpp-modules" / "cpp03" / "ex00.tgz").is_file()
    assert not (tmp_path / "samples" / "common-core" / "cpp03.pdf").exists() and library.checked() == {"cpp03"}


def test_a_pdf_that_is_already_filed_is_not_downloaded_again(tmp_path):
    site = FakeSite()
    site.add_project("cpp-module-03", "CPP Module 03")
    (tmp_path / "samples" / "common-core" / "cpp-modules").mkdir(parents=True)
    (tmp_path / "samples" / "common-core" / "cpp-modules" / "cpp03.pdf").write_bytes(b"mine")
    cpp = Target("common-core", project("cpp-module-03", 1), group="cpp-modules")
    run_scrape(tmp_path, site, [cpp])
    assert (tmp_path / "samples" / "common-core" / "cpp-modules" / "cpp03.pdf").read_bytes() == b"mine"
    assert [p.name for p in (tmp_path / "samples" / "common-core").rglob("*.pdf")] == ["cpp03.pdf"]


# ------------------------------------------------------------------------------------------------ reorganizing


def laid_out(tmp_path: Path, *files: str) -> Library:
    for rel in files:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PDF)
    return Library(tmp_path / "samples", tmp_path / "artifacts")


def test_the_pdfs_and_artifacts_you_have_are_filed_in_the_folders_of_their_series(tmp_path):
    library = laid_out(tmp_path, "samples/common-core/cpp00.pdf", "samples/common-core/cpp01.pdf", "samples/common-core/libft.pdf",
                       "artifacts/cpp00/ex00.tgz", "artifacts/libft/tests.tgz")
    plan = LayoutPlanner().place([*targets("common-core", "cpp-module-00", "cpp-module-01", "libft")])
    reorganizer = Reorganizer(library)
    moves = reorganizer.moves(plan)
    assert len(moves) == 3                                                        # two PDFs and one artifact folder; libft is where it should be
    assert len(reorganizer.apply(moves)) == 3
    assert (tmp_path / "samples/common-core/cpp-modules/cpp00.pdf").is_file() and (tmp_path / "samples/common-core/cpp-modules/cpp01.pdf").is_file()
    assert (tmp_path / "samples/common-core/libft.pdf").is_file() and not (tmp_path / "samples/common-core/cpp00.pdf").exists()
    assert (tmp_path / "artifacts/cpp-modules/cpp00/ex00.tgz").is_file() and (tmp_path / "artifacts/libft/tests.tgz").is_file()
    assert reorganizer.moves(plan) == []                                          # and a second time there is nothing left to do


def test_a_move_never_replaces_a_file_and_never_crosses_a_track(tmp_path):
    library = laid_out(tmp_path, "samples/common-core/cpp00.pdf", "samples/common-core/cpp-modules/cpp00.pdf", "samples/rncp/kfs1.pdf")
    plan = [*LayoutPlanner().place(targets("common-core", "cpp-module-00", "cpp-module-01")),
            *LayoutPlanner().place(targets("post-common-core", "kfs-1", "kfs-2"))]
    assert Reorganizer(library).moves(plan) == []                                 # the target of cpp00 is taken; kfs1 is in another track than planned


def test_the_file_keeps_its_own_name_and_empty_folders_are_not_left_behind(tmp_path):
    library = laid_out(tmp_path, "samples/common-core/CPP00.pdf", "artifacts/cpp00/x.tgz")
    plan = LayoutPlanner().place(targets("common-core", "cpp-module-00", "cpp-module-01"))
    Reorganizer(library).apply(Reorganizer(library).moves(plan))
    assert (tmp_path / "samples/common-core/cpp-modules/CPP00.pdf").is_file()
    assert not (tmp_path / "artifacts" / "cpp00").exists()


def test_the_command_lists_the_moves_and_a_dry_run_moves_nothing(tmp_path):
    library = laid_out(tmp_path, "samples/common-core/cpp00.pdf")
    plan = LayoutPlanner().place(targets("common-core", "cpp-module-00", "cpp-module-01"))
    reporter = Buffer()
    ReorganizeCommand(plan, library, reporter, dry_run=True).execute()
    assert "samples/common-core/cpp00.pdf  ->  samples/common-core/cpp-modules/cpp00.pdf" in reporter.text and "dry run" in reporter.text
    assert (tmp_path / "samples/common-core/cpp00.pdf").is_file()
    done = Buffer()
    ReorganizeCommand(plan, library, done).execute()
    assert "1 of 1 move(s) done" in done.text and (tmp_path / "samples/common-core/cpp-modules/cpp00.pdf").is_file()
    again = Buffer()
    ReorganizeCommand(plan, library, again).execute()
    assert "already in the folder of its series" in again.text


def test_the_plan_says_how_many_are_not_in_their_folder(tmp_path):
    from scraper.cli.parser import CommandFactory, build_parser
    from tests.scraper.test_scraper import settings
    laid_out(tmp_path, "samples/common-core/cpp00.pdf")
    reporter = Buffer()
    CommandFactory(settings(tmp_path), reporter).create(build_parser().parse_args(["--dry-run", "--track", "common-core"])).execute()
    assert "not in the folder of their series" in reporter.text and "--reorganize" in reporter.text
    assert "samples/common-core/cpp-modules/cpp01.pdf" in reporter.text            # a missing one is listed where it will go
    assert TRACKS                                                                   # (the three tracks are still the folders of samples/)


def test_the_folder_of_a_piscine_is_never_moved_into_itself(tmp_path):
    day0 = project("django-0-initiation", 2)
    piscine = project("piscine-django", 1, day0)
    placed = LayoutPlanner().place([Target("rncp", piscine), Target("rncp", day0, piscine)])
    library = laid_out(tmp_path, "artifacts/piscine-django/django-0-initiation/x.tgz")      # the folder of the series exists, it is not the piscine's own
    assert Reorganizer(library).moves(placed) == []
    flat = laid_out(tmp_path / "other", "artifacts/django-0-initiation/x.tgz")
    moves = Reorganizer(flat).moves(placed)
    assert [(m.source.name, m.destination.parent.name) for m in moves] == [("django-0-initiation", "piscine-django")]
