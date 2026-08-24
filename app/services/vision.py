import base64
import time
from pathlib import Path
from typing import List

import fitz  # PyMuPDF
import requests
from loguru import logger

from app.config import Settings


class VisionError(RuntimeError):
    pass


def _annotation_to_text(annotation):
    # type: (dict) -> str
    if not annotation:
        return ""
    full_text = annotation.get("fullText")
    if full_text:
        return full_text.strip()

    blocks = []
    for block in annotation.get("blocks", []):
        for line in block.get("lines", []):
            words = [w.get("text", "") for w in line.get("words", []) if w.get("text")]
            if words:
                blocks.append(" ".join(words))
            elif line.get("text"):
                blocks.append(line["text"])
        blocks.append("")
    return "\n".join(blocks).strip()


def _parse_ocr_response(payload):
    # type: (dict) -> str
    result = payload.get("result")
    if result is None:
        return ""

    if isinstance(result, dict):
        text = _annotation_to_text(result.get("textAnnotation") or {})
        if text:
            return text
        pages = result.get("pages") or []
        parts = [
            _annotation_to_text(page.get("textAnnotation") or page)
            for page in pages
            if isinstance(page, dict)
        ]
        return "\n".join(part for part in parts if part).strip()

    if isinstance(result, list):
        parts = []
        for item in result:
            if not isinstance(item, dict):
                continue
            part = _annotation_to_text(item.get("textAnnotation") or item)
            if part:
                parts.append(part)
        return "\n".join(parts).strip()

    return ""


def _page_to_jpeg_bytes(page, dpi):
    # type: (fitz.Page, int) -> bytes
    zoom = float(dpi) / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return pix.tobytes("jpeg")


def _ocr_image_bytes(image_bytes, settings, mime_type="jpeg"):
    # type: (bytes, Settings, str) -> str
    # Sync recognizeText: JPEG/PNG work; multi-page PDF often fails
    # (page limit 1 / Can't decode image for scanned PDFs).
    language_codes = settings.vision_language_codes_list
    content = base64.b64encode(image_bytes).decode("utf-8")
    response = requests.post(
        settings.yandex_vision_api_url,
        headers={
            "Authorization": "Api-Key {}".format(settings.yandex_api_key),
            "Content-Type": "application/json",
            "x-folder-id": settings.yandex_folder_id,
        },
        json={
            "mimeType": mime_type,
            "languageCodes": language_codes,
            "model": "page",
            "content": content,
        },
        timeout=settings.vision_http_timeout_seconds,
    )
    if response.status_code != 200:
        raise VisionError(
            "Vision OCR error: {} {}".format(response.status_code, response.text)
        )

    text = _parse_ocr_response(response.json())
    if not text:
        raise VisionError("Vision OCR returned empty text")
    return text


def text_to_atoms(text):
    # type: (str) -> List[str]
    """Split OCR/plain text into atoms like DOCX paragraphs (non-empty lines)."""
    atoms = []  # type: List[str]
    for line in text.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if line:
            atoms.append(line)
    return atoms


def extract_pdf_atoms_with_vision(path, settings):
    # type: (Path, Settings) -> List[str]
    """
    OCR scanned PDF: render each page to JPEG, sync Vision, then atomize
    like a Word document for the existing GPT blocking pipeline.
    """
    dpi = int(settings.vision_ocr_dpi)
    interval = float(settings.vision_request_interval_seconds)
    page_texts = []  # type: List[str]

    with fitz.open(str(path)) as doc:
        page_count = doc.page_count
        logger.info(
            "Vision OCR JPEG pages={} dpi={} languageCodes={} interval_s={}",
            page_count,
            dpi,
            settings.vision_language_codes_list,
            interval,
        )
        for page_index in range(page_count):
            if page_index > 0 and interval > 0:
                # Sync OCR quota is typically 1 request/sec.
                time.sleep(interval)
            jpeg_bytes = _page_to_jpeg_bytes(doc[page_index], dpi)
            logger.info(
                "Vision OCR page {}/{} jpeg_bytes={}",
                page_index + 1,
                page_count,
                len(jpeg_bytes),
            )
            page_text = _ocr_image_bytes(jpeg_bytes, settings, mime_type="jpeg")
            page_texts.append(page_text)

    text = "\n\n".join(page_texts)
    atoms = text_to_atoms(text)
    logger.info(
        "Vision OCR done pages={} text_chars={} atoms={}",
        len(page_texts),
        len(text),
        len(atoms),
    )
    return atoms


def extract_text_with_vision(path, settings):
    # type: (Path, Settings) -> str
    return "\n".join(extract_pdf_atoms_with_vision(path, settings))
