"""src/sandbox/request: which requests the runner accepts."""

from pathlib import Path

import pytest
from sandbox.request.roots import AllowedRoots
from sandbox.request.validator import RequestValidator

MAX_TIMEOUT = 300


@pytest.fixture
def validator(tmp_path):
    return RequestValidator(AllowedRoots([tmp_path]), MAX_TIMEOUT)


def test_the_allowed_roots_come_from_the_environment(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert AllowedRoots.from_environment({"ALLOWED_ROOTS": f"{a}::{b}"}).roots == [a.resolve(), b.resolve()]
    assert AllowedRoots.from_environment({"WORKSPACE": str(a)}).roots == [a.resolve()]
    assert AllowedRoots.from_environment({}).roots == [Path("/workspace").resolve()]


def test_request_validation(validator, tmp_path):
    ok = validator.parse({"argv": ["ls"], "cwd": str(tmp_path), "timeout": 9999})
    assert ok.timeout == MAX_TIMEOUT and ok.argv == ["ls"] and ok.cwd == tmp_path.resolve() and ok.stdin == "" and ok.env == {}
    for bad in (
        {"argv": [], "cwd": str(tmp_path)},
        {"argv": ["ls", 1], "cwd": str(tmp_path)},
        {"argv": ["ls"], "cwd": "/etc"},
        {"argv": ["ls"], "cwd": str(tmp_path / ".." )},
        {"argv": ["ls"], "cwd": str(tmp_path / "missing")},
    ):
        with pytest.raises(ValueError):
            validator.parse(bad)


# ---------------------------------------------------------------- SUBJECTS_DIR: the one variable a request may add


def test_a_request_may_add_subjects_dir_only_for_a_folder_inside_the_allowed_roots(validator, tmp_path):
    folder = tmp_path / "abc123" / "subjects"
    folder.mkdir(parents=True)
    assert validator.parse_env({}) == {} and validator.parse_env({"env": None}) == {} and validator.parse_env({"env": {}}) == {}
    assert validator.parse_env({"env": {"SUBJECTS_DIR": str(folder)}}) == {"SUBJECTS_DIR": str(folder.resolve())}
    for bad in (
        {"env": {"SUBJECTS_DIR": "/etc"}},                                     # outside the allowed roots
        {"env": {"SUBJECTS_DIR": str(tmp_path / ".." / "etc")}},
        {"env": {"SUBJECTS_DIR": str(tmp_path / "missing")}},                  # not an existing folder
        {"env": {"SUBJECTS_DIR": str(folder / "x.pdf")}},
        {"env": {"SUBJECTS_DIR": 5}},
        {"env": {"LD_PRELOAD": str(folder)}},                                  # no other variable can be set, ever
        {"env": {"PATH": str(folder)}},
        {"env": {"DOCKER_HOST": "tcp://evil:2375"}},
        {"env": ["SUBJECTS_DIR"]},
    ):
        with pytest.raises(ValueError):
            validator.parse_env(bad)


def test_the_parsed_request_carries_the_subjects_dir(validator, tmp_path):
    (tmp_path / "subjects").mkdir()
    request = validator.parse({"argv": ["ls"], "cwd": str(tmp_path), "env": {"SUBJECTS_DIR": str(tmp_path / "subjects")}})
    assert request.env == {"SUBJECTS_DIR": str((tmp_path / "subjects").resolve())}


def test_a_request_can_never_choose_the_display(validator):
    with pytest.raises(ValueError, match="cannot be set"):
        validator.parse_env({"env": {"DISPLAY": "evil:0"}})
