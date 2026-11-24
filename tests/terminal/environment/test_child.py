"""src/terminal/environment/child.py: the only environment claude gets."""

from dataclasses import replace

from terminal.environment.child import ChildEnvironment
from terminal.settings.settings import Settings
from tests.terminal.fakes import FakeDisplay, environment_of


def child(world, display, **changes):
    return ChildEnvironment(replace(world.settings, **changes), display)


def test_the_child_gets_no_secrets(world, display):
    env = child(world, display).build()
    assert not any(k in env for k in ("ANTHROPIC_API_KEY", "LLM_API_KEY", "TERMINAL_TOKEN", "EDITOR_TOKEN"))
    assert env["TERM"] == "xterm-256color" and env["HOME"] == str(world.tmp / "home") and env["DOCKER_CONFIG"].endswith("/.docker")
    assert env["CLAUDE_CONFIG_DIR"] == f"{world.tmp / 'home'}/.claude" and env["DISABLE_TELEMETRY"] == "1"


def test_the_child_hands_on_the_docker_daemon_address_only_when_set(world, display):
    assert "DOCKER_HOST" not in child(world, display).build()
    assert child(world, display, docker_host="tcp://dind:2375").build()["DOCKER_HOST"] == "tcp://dind:2375"
    assert Settings.from_environment(environment_of(world.tmp, DOCKER_HOST="tcp://dind:2375")).docker_host == "tcp://dind:2375"


def test_the_agent_reaches_the_children_only_when_the_operator_set_one(world, display):
    assert "SSH_AUTH_SOCK" not in child(world, display).build()
    assert child(world, display, ssh_auth_sock="/tmp/ssh-agent.sock").build()["SSH_AUTH_SOCK"] == "/tmp/ssh-agent.sock"
    assert Settings.from_environment(environment_of(world.tmp, SSH_AUTH_SOCK="/tmp/a.sock")).ssh_auth_sock == "/tmp/a.sock"


def test_claude_finds_the_pdfs_of_its_review_in_subjects_dir(world, display):
    env = child(world, display)
    assert env.build("sess-pdf002")["SUBJECTS_DIR"] == str(world.subjects / "sess-pdf002")
    assert "SUBJECTS_DIR" not in env.build() and "SUBJECTS_DIR" not in env.build("../../etc")


def test_the_environment_in_a_project_names_the_report_folder_and_trusts_only_that_project(world, display):
    env = child(world, display)
    project = world.tmp / "projects" / "libft"
    inside = env.build("sess-liv009", project)
    assert inside["REPORT_DIR"] == str(world.reports / "sess-liv009")
    assert (inside["GIT_CONFIG_COUNT"], inside["GIT_CONFIG_KEY_0"], inside["GIT_CONFIG_VALUE_0"]) == ("1", "safe.directory", str(project))
    assert "GIT_CONFIG_COUNT" not in env.build("sess-liv009") and "REPORT_DIR" not in env.build("sess-liv009")
    assert "REPORT_DIR" not in env.build("../../etc", project)                              # (an unusable session id gets no folder)
    assert not any(k in inside for k in ("TERMINAL_TOKEN", "ANTHROPIC_API_KEY", "LLM_API_KEY"))


def test_a_program_with_a_window_gets_the_virtual_display_when_the_image_has_one(world):
    display = FakeDisplay({"DISPLAY": ":99"})
    env = ChildEnvironment(world.settings, display)
    assert env.build()["DISPLAY"] == ":99" and env.build("sess-disp01", world.repo)["DISPLAY"] == ":99"


def test_no_display_and_nothing_else_changes_when_the_image_has_none(world, display):
    env = ChildEnvironment(world.settings, display)
    assert "DISPLAY" not in env.build() and env.build() == env.plain()


def test_the_plain_environment_never_starts_a_display(world):
    class Boom:
        def environment(self):
            raise AssertionError("a display was asked for")

    assert "DISPLAY" not in ChildEnvironment(world.settings, Boom()).plain()
