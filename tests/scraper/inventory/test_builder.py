"""src/scraper/inventory: the PlanReport (one data object), the builder that counts it, and the --dry-run text made from it."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from scraper.cli.commands import PlanCommand
from scraper.cli.parser import CommandFactory, build_parser
from scraper.inventory.builder import PlanReportBuilder
from scraper.inventory.report import ArtifactsReport, MissingSubject, PlanReport, TrackReport
from scraper.plan.catalog import Catalog
from scraper.plan.tracks import build_plan
from scraper.storage.library import Library
from tests.scraper.support import make_world
from tests.scraper.test_scraper import Buffer


def build(world, *, targets=None, unassigned=False, **overrides) -> PlanReport:
    settings = replace(world.settings, **overrides)
    catalog = Catalog.load(settings.data_dir / "projects_21.json")
    plan = build_plan(catalog, settings.data_dir)
    library = Library(settings.samples_dir, settings.artifacts_dir)
    return PlanReportBuilder(plan, catalog, library, settings).build(plan.targets if targets is None else targets, unassigned=unassigned)


def test_the_report_counts_each_track_that_has_projects(world):
    report = build(world)
    assert [(t.track, t.label, t.total, t.with_pdf, len(t.missing)) for t in report.tracks] == [
        ("common-core", "Common Core", 3, 0, 3), ("post-common-core", "Post Common Core", 1, 0, 1), ("rncp", "RNCP", 3, 0, 3)]
    assert report.tracks[0].missing[0] == MissingSubject("cpp00", "common-core/cpp-modules/cpp00.pdf", "cpp-module-00")
    assert report.unknown == ["ft_lex"] and report.tracks[1].unknown == ("ft_lex",) and report.tracks[0].unknown == ()
    assert (report.misplaced, report.to_visit, report.unassigned) == (0, 7, None)


def test_a_track_without_projects_is_left_out(world):
    plan_of_rncp = [t for t in build_plan(Catalog.load(world.settings.data_dir / "projects_21.json"), world.settings.data_dir).targets if t.track == "rncp"]
    assert [t.track for t in build(world, targets=plan_of_rncp).tracks] == ["rncp"]
    assert build(world, targets=[]).tracks == ()


def test_what_is_on_disk_changes_the_numbers_and_not_only_the_missing_list(world):
    world.pdf("common-core/libft.pdf")
    world.pdf("common-core/cpp00.pdf")                                                # (flat: it belongs in cpp-modules/)
    Library(world.tmp / "samples", world.tmp / "artifacts").mark_checked("libft")
    report = build(world)
    assert (report.tracks[0].with_pdf, [m.name for m in report.tracks[0].missing]) == (2, ["cpp01"])
    assert report.misplaced == 1
    assert report.artifacts == ArtifactsReport(checked=1, to_visit=6) and report.to_visit == 6      # (libft needs no visit: PDF there, page read)


def test_without_artifacts_a_pdf_that_is_there_needs_no_visit_and_the_report_has_no_artifacts_part(world):
    world.pdf("common-core/libft.pdf")
    report = build(world, with_artifacts=False)
    assert report.artifacts is None and report.to_visit == 6


def test_the_projects_of_the_catalog_that_are_in_no_track_can_be_listed(world):
    catalog = world.settings.data_dir / "projects_21.json"
    data = json.loads(catalog.read_text())
    data["projects"] += [{"id": 90, "name": "Fract'ol", "slug": "42cursus-fract-ol", "children": []},
                         {"id": 91, "name": "Exam Rank 03", "slug": "42cursus-exam-rank-03", "children": []},
                         {"id": 92, "name": "Not cursus", "slug": "other-thing", "children": []}]
    catalog.write_text(json.dumps(data))
    assert build(world, unassigned=True).unassigned == ("42cursus-fract-ol",) and build(world).unassigned is None


def test_building_the_report_asks_the_intra_nothing_and_writes_nothing(world):
    build(world, unassigned=True)
    assert world.site.requests == [] and not (world.tmp / "artifacts").exists() and not (world.tmp / "samples").exists()


# ------------------------------------------------------------------------------------------- the text of --dry-run


def test_the_dry_run_text_is_made_from_the_report_and_nothing_else(tmp_path):
    report = PlanReport(
        tracks=(TrackReport("rncp", "RNCP", 2, 1, (MissingSubject("a", "rncp/grp/a.pdf", "42cursus-a"),), ("ft_x",)),),
        artifacts=ArtifactsReport(checked=1, to_visit=1), misplaced=2, to_visit=1, unassigned=("42cursus-q",))
    out = Buffer()
    PlanCommand(report, Library(tmp_path / "samples", tmp_path / "artifacts"), out).execute()
    assert out.lines == [
        "\nrncp: 2 project(s), 1 with a PDF, 1 missing",
        "  + samples/rncp/grp/a.pdf   (42cursus-a)",
        "  ? ft_x: not in the catalog (data/projects_21.json)",
        "\nartifacts: 1 project(s) already checked, 1 to visit (they go to artifacts/[<group>/]<name>/)",
        "\n2 PDF(s) or artifact folder(s) are not in the folder of their series: `make samples ARGS=--reorganize` files them "
        "(add --dry-run to see the moves first).",
        "\n1 project page(s) would be visited. Nothing was downloaded (dry run).",
        "\n1 42cursus project(s) of the catalog are in no track (add the ones you want to data/post-common-core.txt):",
        "  42cursus-q"]


def test_a_report_with_nothing_to_say_prints_only_the_visits(tmp_path):
    out = Buffer()
    PlanCommand(PlanReport((), None, 0, 0), Library(tmp_path / "samples", tmp_path / "artifacts"), out).execute()
    assert out.lines == ["\n0 project page(s) would be visited. Nothing was downloaded (dry run)."]


@pytest.mark.parametrize("track", ["common-core", "post-common-core", "rncp"])
def test_the_command_line_and_the_service_tell_the_same_numbers(tmp_path, track):
    world = make_world(tmp_path)
    world.pdf("common-core/libft.pdf")
    out = Buffer()
    CommandFactory(world.settings, out).create(build_parser().parse_args(["--dry-run", "--track", track])).execute()
    answer = next(t for t in world.get("/plan", track=track).json()["tracks"])
    assert f"\n{track}: {answer['total']} project(s), {answer['with_pdf']} with a PDF, {len(answer['missing'])} missing" in out.lines
    for missing in answer["missing"]:
        assert f"  + samples/{missing['path']}   ({missing['slug']})" in out.lines
