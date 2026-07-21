from dataclasses import dataclass
from pathlib import Path
from typing import List

import fitz  # PyMuPDF

from app.config import Settings


@dataclass
class PdfTextResult(object):
    text: str
    page_count: int
    avg_chars_per_page: float
    image_heavy_ratio: float
    use_vision: bool
    reason: str


def _page_is_image_heavy(page):
    images = page.get_images(full=True)
    if not images:
        return False
    page_area = max(page.rect.width * page.rect.height, 1.0)
    large = 0
    for img in images:
        xref = img[0]
        try:
            info = page.parent.extract_image(xref)
        except Exception:
            continue
        width = info.get("width") or 0
        height = info.get("height") or 0
        if width * height >= page_area * 0.35:
            large += 1
    return large > 0


def extract_pdf_page_atoms(path):
    # type: (Path) -> List[str]
    """One atom per PDF page (embedded text layer)."""
    atoms = []  # type: List[str]
    with fitz.open(str(path)) as doc:
        for page in doc:
            text = (page.get_text("text") or "").strip()
            atoms.append(text)
    return atoms


def analyze_pdf(path, settings):
    # type: (Path, Settings) -> PdfTextResult
    with fitz.open(str(path)) as doc:
        page_count = doc.page_count
        if page_count == 0:
            return PdfTextResult(
                text="",
                page_count=0,
                avg_chars_per_page=0.0,
                image_heavy_ratio=0.0,
                use_vision=True,
                reason="empty_pdf",
            )

        page_texts = []
        image_heavy_pages = 0
        for page in doc:
            page_texts.append(page.get_text("text") or "")
            if _page_is_image_heavy(page):
                image_heavy_pages += 1

        text = "\n".join(t.strip() for t in page_texts if t.strip()).strip()
        avg_chars = len(text) / float(page_count)
        image_ratio = image_heavy_pages / float(page_count)

        if settings.pdf_force_vision:
            use_vision, reason = True, "force_vision"
        elif settings.pdf_force_text:
            use_vision, reason = False, "force_text"
        elif avg_chars < settings.pdf_min_chars_per_page:
            use_vision, reason = True, "low_text_density"
        elif image_ratio >= settings.pdf_scan_image_page_ratio:
            use_vision, reason = True, "image_heavy"
        else:
            use_vision, reason = False, "embedded_text"

        return PdfTextResult(
            text=text,
            page_count=page_count,
            avg_chars_per_page=avg_chars,
            image_heavy_ratio=image_ratio,
            use_vision=use_vision,
            reason=reason,
        )
