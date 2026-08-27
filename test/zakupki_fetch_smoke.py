# -*- coding: utf-8 -*-
"""Smoke-test zakupki search + printForm text extraction (no GPT)."""

from __future__ import print_function

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402
from app.services.zakupki import fetch_zakupki_print_atoms  # noqa: E402


def main():
    document_id = sys.argv[1] if len(sys.argv) > 1 else "32616026950"
    # Local Windows often has SSL intercept; VPS should keep verify=true.
    settings = Settings(
        _env_file=str(ROOT / ".env"),
        zakupki_ssl_verify=False,
    )
    atoms, print_url, search_url = fetch_zakupki_print_atoms(document_id, settings)
    text = "\n".join(atoms)
    print("search_url:", search_url)
    print("print_url:", print_url)
    print("atoms:", len(atoms), "chars:", len(text))
    print("---")
    print(text[:1500])
    out = ROOT / "test" / "zakupki_print_sample.txt"
    out.write_text(text, encoding="utf-8")
    print("saved:", out)


if __name__ == "__main__":
    main()
