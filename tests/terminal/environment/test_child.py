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


def test_without_a_gateway_claude_keeps_its_own_login(world, display):
    env = child(world, display).build()
    assert not any(k in env for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"))


def test_on_a_mac_claude_is_sent_to_the_apple_gateway_with_its_placeholder_key(world, display):
    env = child(world, display, claude_gateway_url="http://host.docker.internal:18281", claude_gateway_token="floodgate").build("sess-gate01", world.repo)
    assert env["ANTHROPIC_BASE_URL"] == "http://host.docker.internal:18281" and env["ANTHROPIC_AUTH_TOKEN"] == "floodgate"
    assert not any(k in env for k in ("ANTHROPIC_API_KEY", "LLM_API_KEY", "TERMINAL_TOKEN", "EDITOR_TOKEN")), "still no secret of the service"
    plain = child(world, display, claude_gateway_url="http://gw:1", claude_gateway_token="floodgate").plain()      # the headless review and the editor too
    assert plain["ANTHROPIC_BASE_URL"] == "http://gw:1"


def test_a_gateway_without_a_key_sets_the_address_only_and_a_key_without_an_address_sets_nothing(world, display):
    only_url = child(world, display, claude_gateway_url="http://gw:1").build()
    assert only_url["ANTHROPIC_BASE_URL"] == "http://gw:1" and "ANTHROPIC_AUTH_TOKEN" not in only_url
    only_key = child(world, display, claude_gateway_token="floodgate").build()
    assert "ANTHROPIC_BASE_URL" not in only_key and "ANTHROPIC_AUTH_TOKEN" not in only_key


def test_the_gateway_is_read_from_the_variables_the_apple_file_sets(world):
    settings = Settings.from_environment(environment_of(world.tmp, CLAUDE_GATEWAY_URL="http://host.docker.internal:18281", CLAUDE_GATEWAY_TOKEN="floodgate"))
    assert (settings.claude_gateway_url, settings.claude_gateway_token) == ("http://host.docker.internal:18281", "floodgate")
    assert Settings.from_environment(environment_of(world.tmp)).claude_gateway_url == ""


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


def test_a_process_the_editor_starts_gets_the_same_gateway_when_it_builds_the_environment_again(world, display):
    """The AI Review button opens a terminal that runs `editor_launcher claude`: it builds claude's environment from the one the editor
    gave it. Before, that one lacked the gateway setting, so the claude it started was a plain one that asked you to log in."""
    gateway = {"claude_gateway_url": "http://host.docker.internal:18281", "claude_gateway_token": "floodgate"}
    editor_env = child(world, display, **gateway).build()
    launcher = Settings.from_environment({**environment_of(world.tmp), **editor_env})
    assert (launcher.claude_gateway_url, launcher.claude_gateway_token) == tuple(gateway.values())
    started = ChildEnvironment(launcher, display).build("sess-gate02", world.repo)
    assert started["ANTHROPIC_BASE_URL"] == gateway["claude_gateway_url"] and started["ANTHROPIC_AUTH_TOKEN"] == "floodgate"


def test_without_a_gateway_the_editor_hands_on_no_gateway_setting_at_all(world, display):
    env = child(world, display).build()
    assert not any(k in env for k in ("CLAUDE_GATEWAY_URL", "CLAUDE_GATEWAY_TOKEN"))
