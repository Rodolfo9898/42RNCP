"""Debug dumps of the fetched pages. NullDumper means callers never need an `if dump_html:`."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from scraper.core.utils import safe_name


class PageDumper(ABC):
    @abstractmethod
    def save(self, name: str, html: str) -> None:
        ...


class NullDumper(PageDumper):
    def save(self, name: str, html: str) -> None:
        pass


class HtmlDumper(PageDumper):
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def save(self, name: str, html: str) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"{safe_name(name)}.html").write_text(html, encoding="utf-8")
