"""Settings: everything configurable, as one immutable object handed to whoever needs it."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]       # the repository (src/scraper/core/config.py)
DATA = Path(__file__).resolve().parents[1] / "data"


@dataclass(frozen=True)
class Settings:
    login: str | None = None
    password: str | None = None
    samples_dir: Path = ROOT / "samples"
    artifacts_dir: Path = ROOT / "artifacts"
    data_dir: Path = DATA
    lang: str = "en"
    delay: float = 1.5
    headless: bool = True
    browser_channel: str = "chrome"
    with_artifacts: bool = True
    with_children: bool = True
    with_experience: bool = False
    session_dir: Path = ROOT / ".session"            # what the browser login leaves: the cookies and the user-agent that goes with them
    state_file: Path | None = None                   # the cookies (Playwright's storage state); default: <session_dir>/state.json
    user_agent_file: Path | None = None              # default: <session_dir>/user_agent.txt
    debug_dir: Path = ROOT / ".debug"

    def __post_init__(self) -> None:
        """The two session files follow `session_dir` unless a path was given for them."""
        for name, default in (("state_file", "state.json"), ("user_agent_file", "user_agent.txt")):
            if getattr(self, name) is None:
                object.__setattr__(self, name, self.session_dir / default)

    @classmethod
    def from_env(cls, *, lang: str | None = None, delay: float | None = None, headed: bool = False,
                 with_artifacts: bool = True, with_children: bool = True, with_experience: bool = False,
                 environ: Mapping[str, str] | None = None) -> Settings:
        """Settings from the environment (the .env of the repository), letting command-line values win."""
        env = (os.environ if environ is None else environ).get
        return cls(
            login=env("INTRA_LOGIN") or None,
            password=env("INTRA_PASSWORD") or None,
            samples_dir=Path(env("SAMPLES_DIR") or ROOT / "samples").expanduser(),
            artifacts_dir=Path(env("ARTIFACTS_DIR") or ROOT / "artifacts").expanduser(),
            session_dir=Path(env("SESSION_DIR") or ROOT / ".session").expanduser(),
            lang=(lang or env("SUBJECT_LANG") or "en").lower(),
            delay=delay if delay is not None else float(env("SCRAPE_DELAY") or 1.5),
            headless=not headed and env("HEADLESS", "true").lower() != "false",
            browser_channel=env("BROWSER_CHANNEL", "chrome"),
            with_artifacts=with_artifacts, with_children=with_children, with_experience=with_experience,
        )
