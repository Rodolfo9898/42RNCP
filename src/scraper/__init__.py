"""Fills `samples/` (the subject PDFs) and `artifacts/` (the files that come with a project) from the 42 intra.

The command line (`make samples`, see the README, "Getting the subjects") runs on your machine, not in Docker: it needs your intra
login, which the containers never get. `make samples-login` logs in once and saves the session; the scraper service (`server/`, started
by `scraper_server.py`) reuses that session, read-only, to download for the editor, and never logs in itself.
"""
