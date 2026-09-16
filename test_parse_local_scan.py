# -*- coding: utf-8 -*-
"""
Локальная диагностика PDF без HTTP: analyze → Vision OCR (страницы) → опционально GPT.

Примеры:
    python test_parse_local_scan.py path\\to\\scan.pdf
    python test_parse_local_scan.py path\\to\\scan.pdf --ocr-pages 1
    python test_parse_local_scan.py path\\to\\scan.pdf --full
"""

from __future__ import print_function

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description="Local scan PDF diagnose")
    parser.add_argument("pdf", help="Path to PDF")
    parser.add_argument(
        "--ocr-pages",
        type=int,
        default=1,
        help="OCR first N pages (0 = skip OCR). Default 1",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full pipeline: all pages OCR + GPT via process_local_file",
    )
    args = parser.parse_args()

    path = Path(args.pdf).expanduser()
    if not path.is_file():
        raise SystemExit("File not found: {}".format(path))

    from app.config import Settings
    from app.services.pdf_extract import analyze_pdf

    settings = Settings(_env_file=str(ROOT / ".env"))
    analysis = analyze_pdf(path, settings)
    print("file:", path)
    print("size_bytes:", path.stat().st_size)
    print(
        "pages={} use_vision={} reason={} avg_chars={:.1f} image_ratio={:.2f}".format(
            analysis.page_count,
            analysis.use_vision,
            analysis.reason,
            analysis.avg_chars_per_page,
            analysis.image_heavy_ratio,
        )
    )

    if args.full:
        prompt_path = ROOT / "prompt.txt"
        if not prompt_path.is_file():
            prompt_path = ROOT / "Prompt.txt"
        prompt = prompt_path.read_text(encoding="utf-8")
        from app.services.pipeline import process_local_file

        print("Running full process_local_file (OCR all pages + GPT)...")
        result = process_local_file(
            path,
            filename=path.name,
            content_type="application/pdf",
            size_bytes=path.stat().st_size,
            settings=settings,
            prompt=prompt,
        )
        print("success:", result.success)
        print("meta:", result.meta)
        print("fields:", result.fields)
        return

    n = max(0, int(args.ocr_pages))
    if n <= 0:
        return
    if not analysis.use_vision and not settings.pdf_force_vision:
        print("Note: analyzer would NOT use Vision for this file (embedded text path).")

    import fitz
    from app.services.vision import _ocr_image_bytes, _page_to_jpeg_bytes

    out_dir = ROOT / "test" / "vision_ocr_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem

    with fitz.open(str(path)) as doc:
        limit = min(n, doc.page_count)
        for i in range(limit):
            jpeg = _page_to_jpeg_bytes(doc[i], settings.vision_ocr_dpi)
            print(
                "OCR page {}/{} jpeg_bytes={} dpi={}".format(
                    i + 1, doc.page_count, len(jpeg), settings.vision_ocr_dpi
                )
            )
            try:
                text = _ocr_image_bytes(jpeg, settings, mime_type="jpeg")
            except Exception as exc:
                print("FAILED page {}: {}: {}".format(i + 1, type(exc).__name__, exc))
                continue
            print("OK page {} chars={}".format(i + 1, len(text)))
            print(text[:800])
            print("---")
            (out_dir / "{}_p{}_ocr.txt".format(stem, i + 1)).write_text(
                text, encoding="utf-8"
            )


if __name__ == "__main__":
    main()
