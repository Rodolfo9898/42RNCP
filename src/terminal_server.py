"""Main of the terminal service (the `terminal` container): claude's saved report, the subject PDFs, the environment self-test and the
headless review, for the web app. (`python -m editor_launcher` runs the same service next to the editor.)"""

import os

from sandbox.display.xvfb import VirtualDisplay
from terminal.api.app import create_app
from terminal.settings.settings import Settings

app = create_app(Settings.from_environment(os.environ), VirtualDisplay())
