"""POST /reorganizations: file what you have in the folders of its series, or only say what would move."""
from __future__ import annotations

from tests.scraper.support import make_world
from tests.scraper.test_scraper import PDF

MOVES = [{"from": "samples/common-core/cpp00.pdf", "to": "samples/common-core/cpp-modules/cpp00.pdf"},
         {"from": "artifacts/cpp00", "to": "artifacts/cpp-modules/cpp00"},                       # (a project's PDF, then its artifacts)
         {"from": "samples/common-core/cpp01.pdf", "to": "samples/common-core/cpp-modules/cpp01.pdf"}]


def lay_out(world) -> None:
    world.pdf("common-core/cpp00.pdf")
    world.pdf("common-core/cpp01.pdf")
    world.pdf("common-core/libft.pdf")                                        # where it should be
    (world.tmp / "artifacts/cpp00").mkdir(parents=True)
    (world.tmp / "artifacts/cpp00/ex00.tgz").write_bytes(b"x")


def test_a_dry_run_lists_the_moves_relative_to_the_repository_and_moves_nothing(world):
    lay_out(world)
    answer = world.post("/reorganizations", {"dry_run": True})
    assert answer.status_code == 200
    assert answer.json() == {"dry_run": True, "done": 0, "moves": MOVES}
    assert (world.tmp / "samples/common-core/cpp00.pdf").is_file() and (world.tmp / "artifacts/cpp00/ex00.tgz").is_file()
    assert not (world.tmp / "samples/common-core/cpp-modules").exists()


def test_the_default_is_to_look_not_to_move(world):
    lay_out(world)
    assert world.post("/reorganizations").json()["dry_run"] is True and world.post("/reorganizations", {}).json()["done"] == 0
    assert (world.tmp / "samples/common-core/cpp00.pdf").is_file()


def test_a_real_run_moves_the_files_and_says_how_many(world):
    lay_out(world)
    answer = world.post("/reorganizations", {"dry_run": False}).json()
    assert answer == {"dry_run": False, "done": 3, "moves": MOVES}
    assert (world.tmp / "samples/common-core/cpp-modules/cpp00.pdf").read_bytes() == PDF
    assert (world.tmp / "samples/common-core/cpp-modules/cpp01.pdf").is_file() and (world.tmp / "samples/common-core/libft.pdf").is_file()
    assert (world.tmp / "artifacts/cpp-modules/cpp00/ex00.tgz").is_file() and not (world.tmp / "artifacts/cpp00").exists()
    assert not (world.tmp / "samples/common-core/cpp00.pdf").exists()


def test_a_second_run_has_nothing_left_to_do(world):
    lay_out(world)
    world.post("/reorganizations", {"dry_run": False})
    assert world.post("/reorganizations", {"dry_run": False}).json() == {"dry_run": False, "done": 0, "moves": []}


def test_a_move_never_replaces_a_file(world):
    world.pdf("common-core/cpp00.pdf", b"flat")
    world.pdf("common-core/cpp-modules/cpp00.pdf", b"filed")
    answer = world.post("/reorganizations", {"dry_run": False}).json()
    assert answer == {"dry_run": False, "done": 0, "moves": []}
    assert (world.tmp / "samples/common-core/cpp-modules/cpp00.pdf").read_bytes() == b"filed"


def test_the_plan_stops_counting_a_pdf_as_misplaced_once_it_is_filed(world):
    lay_out(world)
    assert world.get("/plan").json()["misplaced"] == 3
    world.post("/reorganizations", {"dry_run": False})
    assert world.get("/plan").json()["misplaced"] == 0


def test_nothing_is_filed_while_a_download_writes_into_the_same_folders(world):
    lay_out(world)
    world.post("/downloads", {"projects": ["darkly"]})
    answer = world.post("/reorganizations", {"dry_run": False})
    assert answer.status_code == 409 and "download is running" in answer.json()["detail"]
    assert (world.tmp / "samples/common-core/cpp00.pdf").is_file()
    world.starter.run()
    assert world.post("/reorganizations", {"dry_run": False}).json()["done"] == 3


def test_it_needs_no_session_because_it_is_offline(tmp_path):
    world = make_world(tmp_path, session=False)
    lay_out(world)
    assert world.post("/reorganizations", {"dry_run": False}).json()["done"] == 3 and world.site.requests == []
