import base64
from pathlib import Path
from typing import List

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

    # Single-page / aggregated: { "textAnnotation": {...} }
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

    # Multi-page list of annotations / page objects
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


def _ocr_pdf_bytes(pdf_bytes, settings):
    # type: (bytes, Settings) -> str
    # recognizeText expects top-level languageCodes (not textDetectionParams).
    language_codes = settings.vision_language_codes_list
    content = base64.b64encode(pdf_bytes).decode("utf-8")
    response = requests.post(
        settings.yandex_vision_api_url,
        headers={
            "Authorization": "Api-Key {}".format(settings.yandex_api_key),
            "Content-Type": "application/json",
            "x-folder-id": settings.yandex_folder_id,
        },
        json={
            "mimeType": "pdf",
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
    """OCR whole PDF once, then atomize text like a Word document."""
    pdf_bytes = path.read_bytes()
    logger.info(
        "Vision OCR whole PDF bytes={} languageCodes={}",
        len(pdf_bytes),
        settings.vision_language_codes_list,
    )
    text = _ocr_pdf_bytes(pdf_bytes, settings)
    atoms = text_to_atoms(text)
    logger.info("Vision OCR done text_chars={} atoms={}", len(text), len(atoms))
    return atoms


def extract_text_with_vision(path, settings):
    # type: (Path, Settings) -> str
    return "\n".join(extract_pdf_atoms_with_vision(path, settings))
