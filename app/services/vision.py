import base64
from pathlib import Path
from typing import List

import fitz  # PyMuPDF
import requests

from app.config import Settings


class VisionError(RuntimeError):
    pass


def _ocr_pdf_bytes(pdf_bytes, settings):
    # type: (bytes, Settings) -> str
    content = base64.b64encode(pdf_bytes).decode("utf-8")
    response = requests.post(
        "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText",
        headers={
            "Authorization": "Api-Key {}".format(settings.yandex_api_key),
            "Content-Type": "application/json",
        },
        json={
            "folderId": settings.yandex_folder_id,
            "mimeType": "application/pdf",
            "content": content,
            "textDetectionParams": {
                "languageCodes": ["ru", "en"],
                "textTypes": ["printed"],
            },
        },
        timeout=120,
    )
    if response.status_code != 200:
        raise VisionError(
            "Vision OCR error: {} {}".format(response.status_code, response.text)
        )

    result = response.json()
    annotation = result.get("result", {}).get("textAnnotation", {})
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


def extract_pdf_page_atoms_with_vision(path, settings):
    # type: (Path, Settings) -> List[str]
    """OCR each PDF page separately -> one atom per page."""
    atoms = []  # type: List[str]
    with fitz.open(str(path)) as src:
        for page_index in range(src.page_count):
            single = fitz.open()
            single.insert_pdf(src, from_page=page_index, to_page=page_index)
            pdf_bytes = single.tobytes()
            single.close()
            atoms.append(_ocr_pdf_bytes(pdf_bytes, settings))
    return atoms


def extract_text_with_vision(path, settings):
    # type: (Path, Settings) -> str
    return "\n".join(extract_pdf_page_atoms_with_vision(path, settings))
