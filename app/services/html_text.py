"""HTML → plain-text atoms for the GPT pipeline."""

from __future__ import annotations

import re
from typing import List

from bs4 import BeautifulSoup


_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "dl",
        "dt",
        "dd",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tr",
        "ul",
    }
)


def html_to_plain_text(html):
    # type: (str) -> str
    """Strip scripts/styles and collapse HTML into readable plain text."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    for tag in soup.find_all(True):
        if tag.name in _BLOCK_TAGS:
            tag.insert_before("\n")
            tag.insert_after("\n")
        elif tag.name == "td":
            tag.insert_before(" ")
            tag.insert_after(" ")

    text = soup.get_text(separator="")
    text = text.replace("\xa0", " ").replace("\u2009", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_to_text_atoms(html):
    # type: (str) -> List[str]
    """
    Non-empty lines as atoms (same idea as DOCX paragraphs).
    Print-form pages are HTML tables; line atoms work well for GPT blocking.
    """
    plain = html_to_plain_text(html)
    atoms = []  # type: List[str]
    for line in plain.splitlines():
        line = line.strip()
        if line:
            atoms.append(line)
    return atoms
