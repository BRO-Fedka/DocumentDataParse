# Vision OCR probe

Script: `vision_ocr_probe.py`

```bash
python test/vision_ocr_probe.py
python test/vision_ocr_probe.py "C:\path\to\scan.pdf"
```

Uses repo `.env` (`YANDEX_API_KEY`, `YANDEX_FOLDER_ID`).

Output: `test/vision_ocr_out/<name>_ocr.txt`

## What works for scanned PDFs

Render each PDF page to JPEG (PyMuPDF) → sync `recognizeText` with `mimeType: "jpeg"`.

The main app (`app/services/vision.py`) uses the same approach.

Sync PDF upload fails:
- `mimeType: pdf` → `Can't decode image`
- `mimeType: application/pdf` on multi-page → `Request pages N, service page limit is 1`
