"""Extracts the title, the first <h1> and every link from an HTML page (stdlib only)."""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin

from scraper.core.models import Link, ParsedPage


class _Extractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.page = ParsedPage()
        self._href: str | None = None
        self._a_text: list[str] = []
        self._h1_text: list[str] | None = None
        self._title_text: list[str] | None = None

    def end_anchor(self) -> None:
        if self._href is not None:
            self.page.links.append(Link(urljoin(self.base_url, self._href), " ".join("".join(self._a_text).split())))
        self._href = None
        self._a_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.end_anchor()
            href = dict(attrs).get("href")
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                self._href = href
        elif tag == "h1" and not self.page.h1:
            self._h1_text = []
        elif tag == "title" and not self.page.title:
            self._title_text = []

    def handle_endtag(self, tag):
        if tag == "a":
            self.end_anchor()
        elif tag == "h1" and self._h1_text is not None:
            self.page.h1 = " ".join(" ".join(self._h1_text).split())
            self._h1_text = None
        elif tag == "title" and self._title_text is not None:
            self.page.title = " ".join(" ".join(self._title_text).split())
            self._title_text = None

    def handle_data(self, data):
        for part in (self._a_text if self._href is not None else None, self._h1_text, self._title_text):
            if part is not None:
                part.append(data)


class PageParser:
    def parse(self, html: str, base_url: str) -> ParsedPage:
        extractor = _Extractor(base_url)
        extractor.feed(html)
        extractor.close()
        extractor.end_anchor()
        return extractor.page
