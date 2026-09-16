# -*- coding: utf-8 -*-
"""
Консольный тест POST /parse.

Примеры:
    python test_parse.py path\\to\\file.pdf
    python test_parse.py file1.pdf file2.docx
    python test_parse.py
        # спросит путь к файлу в консоли

Нужен поднятый API. Настройки из .env: APP_API_KEY, BASE_URL / HOST+PORT.
Промпт: PROMPT_FILE или prompt.txt в корне проекта.
"""

from __future__ import print_function

import json
import mimetypes
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    raise SystemExit("Install requests: pip install requests")

ROOT = Path(__file__).resolve().parent
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_PROMPT_FILE = "prompt.txt"
DEFAULT_USERNAME = "console-parse-test"
DEFAULT_TIMEOUT = 900


def _load_dotenv():
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _base_url():
    explicit = (os.environ.get("BASE_URL") or os.environ.get("API_BASE_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    host = (os.environ.get("HOST") or "127.0.0.1").strip()
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    port = (os.environ.get("PORT") or "8000").strip()
    return "http://{}:{}".format(host, port)


def _load_prompt():
    name = os.environ.get("PROMPT_FILE") or DEFAULT_PROMPT_FILE
    path = ROOT / name
    if not path.is_file():
        alt = ROOT / "Prompt.txt"
        path = alt if alt.is_file() else path
    if not path.is_file():
        raise SystemExit("Prompt file not found: {}".format(path))
    return path.read_text(encoding="utf-8").strip()


def _collect_paths(argv):
    paths = []
    for arg in argv:
        p = Path(arg).expanduser()
        if not p.is_file():
            raise SystemExit("File not found: {}".format(p))
        ext = p.suffix.lower()
        if ext not in (".pdf", ".docx"):
            raise SystemExit("Unsupported extension (need .pdf/.docx): {}".format(p))
        paths.append(p)
    return paths


def main():
    _load_dotenv()
    api_key = (os.environ.get("APP_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("APP_API_KEY is empty — set it in .env or environment")

    username = (os.environ.get("TEST_USERNAME") or DEFAULT_USERNAME).strip()
    prompt = _load_prompt()
    url = "{}/parse".format(_base_url().rstrip("/") or DEFAULT_BASE_URL)

    if len(sys.argv) > 1:
        paths = _collect_paths(sys.argv[1:])
    else:
        raw = input("path to PDF/DOCX (or several, separated by |): ").strip()
        if not raw:
            raise SystemExit("No file path")
        parts = [p.strip() for p in raw.split("|") if p.strip()]
        paths = _collect_paths(parts)

    print("URL:      {}".format(url))
    print("Username: {}".format(username))
    print("Prompt:   {} chars".format(len(prompt)))
    print("Files:    {}".format([str(p) for p in paths]))
    print("-" * 60)
    print("Requesting... (scans: Vision OCR ~1s/page + GPT)")

    opened = []
    try:
        files = []
        for path in paths:
            handle = path.open("rb")
            opened.append(handle)
            mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            files.append(("files", (path.name, handle, mime)))

        response = requests.post(
            url,
            headers={"X-API-Key": api_key},
            data={"username": username, "prompt": prompt},
            files=files,
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise SystemExit("HTTP request failed: {}".format(exc))
    finally:
        for handle in opened:
            try:
                handle.close()
            except Exception:
                pass

    print("HTTP {}".format(response.status_code))
    print("-" * 60)
    try:
        payload = response.json()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    except ValueError:
        print(response.text)


if __name__ == "__main__":
    main()
