"""Fetch contract print-form text from zakupki.gov.ru (FZ-223 registry)."""

from __future__ import annotations

from typing import List, Tuple
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from loguru import logger

from app.config import Settings
from app.services.html_text import html_to_text_atoms

CARD_CSS = "div.search-registry-entry-block.box-shadow-search-input"
PRINT_LINK_CSS = "div.registry-entry__header-top__icon a[href*='printForm']"


class ZakupkiLookupError(ValueError):
    """Wrong number of search cards or missing print link (HTTP 400)."""


def build_search_url(document_id, settings):
    # type: (str, Settings) -> str
    """Put document_id into searchString; keep the rest of the query fixed."""
    template = settings.zakupki_search_url_template
    return template.format(document_id=quote(document_id, safe=""))


def _http_get(url, settings):
    # type: (str, Settings) -> str
    headers = {
        "User-Agent": settings.zakupki_user_agent,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    logger.info("Zakupki GET {}", url)
    response = requests.get(
        url,
        headers=headers,
        timeout=settings.zakupki_http_timeout_seconds,
        verify=settings.zakupki_ssl_verify,
    )
    response.raise_for_status()
    # These pages are UTF-8; do not trust latin-1 default from missing charset.
    response.encoding = "utf-8"
    return response.text


def _absolute_url(href, settings):
    # type: (str, Settings) -> str
    return urljoin(settings.zakupki_base_url.rstrip("/") + "/", href)


def find_print_form_url(search_html, settings):
    # type: (str, Settings) -> str
    """
    Require exactly one registry card; return absolute printForm URL from it.
    """
    soup = BeautifulSoup(search_html or "", "html.parser")
    cards = soup.select(CARD_CSS)
    n = len(cards)
    if n == 0:
        raise ZakupkiLookupError(
            "No registry cards found for document_id (expected exactly 1)"
        )
    if n > 1:
        raise ZakupkiLookupError(
            "Found {} registry cards for document_id (expected exactly 1)".format(n)
        )

    card = cards[0]
    link = card.select_one(PRINT_LINK_CSS)
    if link is None:
        # Fallback: any printForm anchor inside the single card.
        link = card.select_one("a[href*='printForm']")
    if link is None or not link.get("href"):
        raise ZakupkiLookupError(
            "Print-form link not found inside the registry card"
        )

    href = link["href"].strip()
    absolute = _absolute_url(href, settings)
    parsed = urlparse(absolute)
    if not parsed.scheme or not parsed.netloc:
        raise ZakupkiLookupError("Invalid print-form URL: {}".format(href))
    return absolute


def fetch_zakupki_print_atoms(document_id, settings):
    # type: (str, Settings) -> Tuple[List[str], str, str]
    """
    Search → one card → printForm HTML → text atoms.

    Returns (atoms, print_form_url, search_url).
    """
    doc_id = (document_id or "").strip()
    if not doc_id:
        raise ZakupkiLookupError("document_id is empty")

    search_url = build_search_url(doc_id, settings)
    search_html = _http_get(search_url, settings)
    print_url = find_print_form_url(search_html, settings)
    print_html = _http_get(print_url, settings)
    atoms = html_to_text_atoms(print_html)
    if not any(atom.strip() for atom in atoms):
        raise ValueError("Print-form text is empty after HTML cleanup")

    logger.info(
        "Zakupki print form ready document_id={} print_url={} atoms={} chars={}",
        doc_id,
        print_url,
        len(atoms),
        sum(len(a) for a in atoms),
    )
    return atoms, print_url, search_url
