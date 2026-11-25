"""Main of the scraper service (the `scraper` container): the plan of the subject library, and the downloads from the 42 intra, for the web
app. It never logs in: it uses the session that `make samples-login` saved on the person's computer. Refuses to start without SCRAPER_TOKEN."""

import os

from scraper.server.app import create_app
from scraper.server.settings import ServiceSettings

app = create_app(ServiceSettings.from_environment(os.environ))
