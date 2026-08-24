"""
Yandex Vision OCR probe for scanned PDFs.

Finding (Договор 28.pdf, 5 pages, JPEG scans inside):
  - sync whole PDF mime=pdf           -> Can't decode image
  - sync whole PDF mime=application/pdf -> Request pages 5, service page limit is 1
  - sync single-page PDF mime=pdf     -> Can't decode image
  - sync page JPEG mime=jpeg          -> WORKS
  - sync RPS quota = 1 request/sec

Usage (repo root):
  python test/vision_ocr_probe.py
  python test/vision_ocr_probe.py "C:\\path\\to\\file.pdf"
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = Path(r"c:\Users\BRO_Fedka\Downloads\Договор 28.pdf")
OUT_DIR = Path(__file__).resolve().parent / "vision_ocr_out"

SYNC_URL = "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText"
ASYNC_URL = "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeTextAsync"
OPS_URL = "https://operation.api.cloud.yandex.net/operations"
GET_RECOGNITION_URL = "https://ocr.api.cloud.yandex.net/ocr/v1/getRecognition"


def _load_env():
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("YANDEX_API_KEY", "").strip()
    folder_id = os.environ.get("YANDEX_FOLDER_ID", "").strip()
    if not api_key or not folder_id:
        raise SystemExit("Need YANDEX_API_KEY and YANDEX_FOLDER_ID in .env")
    return api_key, folder_id


def _headers(api_key, folder_id):
    return {
        "Authorization": "Api-Key {}".format(api_key),
        "Content-Type": "application/json",
        "x-folder-id": folder_id,
    }


def _extract_text(payload):
    result = payload.get("result")
    if result is None and "textAnnotation" in payload:
        result = payload

    def from_ann(ann):
        if not isinstance(ann, dict):
            return ""
        full = (ann.get("fullText") or "").strip()
        if full:
            return full
        lines = []
        for block in ann.get("blocks") or []:
            for line in block.get("lines") or []:
                if line.get("text"):
                    lines.append(line["text"])
                else:
                    words = [
                        w.get("text", "")
                        for w in (line.get("words") or [])
                        if w.get("text")
                    ]
                    if words:
                        lines.append(" ".join(words))
        return "\n".join(lines).strip()

    if isinstance(result, dict):
        text = from_ann(result.get("textAnnotation") or {})
        if text:
            return text
        pages = result.get("pages") or []
        parts = []
        for page in pages:
            if isinstance(page, dict):
                parts.append(from_ann(page.get("textAnnotation") or page))
        return "\n".join(p for p in parts if p).strip()

    if isinstance(result, list):
        parts = []
        for item in result:
            if not isinstance(item, dict):
                continue
            parts.append(from_ann(item.get("textAnnotation") or item))
        return "\n".join(p for p in parts if p).strip()

    return ""


def sync_recognize(api_key, folder_id, content_b64, mime_type, model="page", langs=None):
    langs = langs or ["ru", "en"]
    # Sync OCR quota is 1 RPS.
    time.sleep(1.1)
    body = {
        "mimeType": mime_type,
        "languageCodes": langs,
        "model": model,
        "content": content_b64,
    }
    resp = requests.post(
        SYNC_URL, headers=_headers(api_key, folder_id), json=body, timeout=180
    )
    payload = resp.json() if resp.content else {}
    return resp.status_code, resp.text, payload


def async_recognize(api_key, folder_id, content_b64, mime_type, model="page", langs=None):
    langs = langs or ["ru", "en"]
    body = {
        "mimeType": mime_type,
        "languageCodes": langs,
        "model": model,
        "content": content_b64,
    }
    resp = requests.post(
        ASYNC_URL, headers=_headers(api_key, folder_id), json=body, timeout=180
    )
    if resp.status_code != 200:
        return resp.status_code, resp.text, {}

    op = resp.json()
    op_id = op.get("id")
    if not op_id:
        return resp.status_code, "no operation id: {}".format(resp.text), {}

    deadline = time.time() + 300
    while time.time() < deadline:
        st = requests.get(
            "{}/{}".format(OPS_URL, op_id),
            headers=_headers(api_key, folder_id),
            timeout=60,
        )
        if st.status_code != 200:
            return st.status_code, st.text, {}
        data = st.json()
        if data.get("done"):
            if data.get("error"):
                return 400, json.dumps(data.get("error"), ensure_ascii=False), data
            gr = requests.get(
                GET_RECOGNITION_URL,
                headers=_headers(api_key, folder_id),
                params={"operationId": op_id},
                timeout=120,
            )
            if gr.status_code == 200:
                return gr.status_code, gr.text, gr.json()
            return 200, json.dumps(data, ensure_ascii=False), data
        time.sleep(1.5)

    return 408, "async timeout op_id={}".format(op_id), {}


def page_jpeg_bytes(doc, page_index, dpi=150):
    page = doc[page_index]
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return pix.tobytes("jpeg")


def ocr_pdf_via_jpeg_pages(api_key, folder_id, doc):
    parts = []
    for i in range(doc.page_count):
        print("OCR JPEG page {}/{}".format(i + 1, doc.page_count))
        img = page_jpeg_bytes(doc, i, dpi=150)
        status, raw, payload = sync_recognize(
            api_key,
            folder_id,
            base64.b64encode(img).decode("ascii"),
            "jpeg",
        )
        text = _extract_text(payload) if status == 200 else ""
        print("  status={} chars={}".format(status, len(text)))
        if status != 200 or not text:
            raise RuntimeError("page {} failed: {}".format(i + 1, raw[:400]))
        parts.append(text)
    return "\n\n".join(parts)


def main():
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    if not pdf_path.is_file():
        raise SystemExit("PDF not found: {}".format(pdf_path))

    api_key, folder_id = _load_env()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("PDF:", pdf_path)
    print("size:", pdf_path.stat().st_size)

    doc = fitz.open(str(pdf_path))
    print("pages:", doc.page_count)

    # Working path first.
    print("\n=== sync JPEG pages (mime=jpeg) ===")
    text = ocr_pdf_via_jpeg_pages(api_key, folder_id, doc)

    out_text = OUT_DIR / (pdf_path.stem + "_ocr.txt")
    out_text.write_text(text, encoding="utf-8")
    print("\nOK saved:", out_text)
    print("Total chars:", len(text))
    print("Preview:\n", text[:600])
    doc.close()


if __name__ == "__main__":
    main()
