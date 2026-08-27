# -*- coding: utf-8 -*-
"""
Интерактивный тест POST /get_document_data.

Запуск (API должен быть поднят):
    python test_get_document_data.py

В консоли вводится document_id; JSON-ответ печатается в консоль.
Настройки берутся из .env / окружения (APP_API_KEY, BASE_URL / HOST+PORT).
"""

from __future__ import print_function

import json
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
DEFAULT_USERNAME = "console-test"
DEFAULT_TIMEOUT = 600


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
    path = ROOT / (os.environ.get("PROMPT_FILE") or DEFAULT_PROMPT_FILE)
    if not path.is_file():
        # Windows / mixed case fallback used by GUI client
        alt = ROOT / "Prompt.txt"
        path = alt if alt.is_file() else path
    if not path.is_file():
        raise SystemExit("Prompt file not found: {}".format(path))
    return path.read_text(encoding="utf-8").strip()


def main():
    _load_dotenv()
    base_url = _base_url() or DEFAULT_BASE_URL
    api_key = (os.environ.get("APP_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("APP_API_KEY is empty — set it in .env or environment")

    username = (os.environ.get("TEST_USERNAME") or DEFAULT_USERNAME).strip()
    prompt = _load_prompt()
    url = "{}/get_document_data".format(base_url.rstrip("/"))

    print("URL:      {}".format(url))
    print("Username: {}".format(username))
    print("Prompt:   {} chars".format(len(prompt)))
    print("-" * 60)
    document_id = input("document_id: ").strip()
    if not document_id:
        raise SystemExit("document_id is empty")

    print("Requesting... (may take a while: zakupki + GPT)")
    try:
        response = requests.post(
            url,
            headers={"X-API-Key": api_key},
            data={
                "username": username,
                "prompt": prompt,
                "document_id": document_id,
            },
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise SystemExit("HTTP request failed: {}".format(exc))

    print("HTTP {}".format(response.status_code))
    print("-" * 60)
    try:
        payload = response.json()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    except ValueError:
        print(response.text)


if __name__ == "__main__":
    main()
