from pathlib import Path
from typing import List

from docx import Document


def _iter_docx_blocks(document):
    """Обходит абзацы и таблицы в порядке их следования в документе."""
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    paragraph_tag = qn("w:p")
    table_tag = qn("w:tbl")

    for child in document.element.body.iterchildren():
        if child.tag == paragraph_tag:
            yield Paragraph(child, document)
        elif child.tag == table_tag:
            yield Table(child, document)


def _table_to_text(table):
    rows = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            text = (cell.text or "").strip()
            if text:
                cells.append(text)
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def extract_docx_atoms(path):
    # type: (Path) -> List[str]
    """Atoms: paragraph or whole table, document order."""
    document = Document(str(path))
    atoms = []  # type: List[str]
    for block in _iter_docx_blocks(document):
        if hasattr(block, "rows"):
            text = _table_to_text(block).strip()
            if text:
                atoms.append(text)
        else:
            text = (block.text or "").strip()
            if text:
                atoms.append(text)
    return atoms


def extract_text_from_docx(path):
    # type: (Path) -> str
    return "\n".join(extract_docx_atoms(path))
