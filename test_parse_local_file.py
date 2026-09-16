# -*- coding: utf-8 -*-
"""
Локальный прогон DOCX/PDF без HTTP (extract + GPT).

    python test_parse_local_file.py path\\to\\file.docx
    python test_parse_local_file.py path\\to\\scan.pdf
"""

from __future__ import print_function

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python test_parse_local_file.py <file.pdf|file.docx>")
    path = Path(sys.argv[1]).expanduser()
    if not path.is_file():
        raise SystemExit("File not found: {}".format(path))

    from app.config import Settings
    from app.services.pipeline import process_local_file

    settings = Settings(_env_file=str(ROOT / ".env"))
    prompt_path = ROOT / "prompt.txt"
    if not prompt_path.is_file():
        prompt_path = ROOT / "Prompt.txt"
    prompt = prompt_path.read_text(encoding="utf-8")

    ext = path.suffix.lower()
    ctype = (
        "application/pdf"
        if ext == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    print("file:", path)
    print("size:", path.stat().st_size)
    print("Running process_local_file...")
    result = process_local_file(
        path,
        filename=path.name,
        content_type=ctype,
        size_bytes=path.stat().st_size,
        settings=settings,
        prompt=prompt,
    )
    print("success:", result.success)
    print("meta:", result.meta)
    print("fields:")
    print(json.dumps(result.fields, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
