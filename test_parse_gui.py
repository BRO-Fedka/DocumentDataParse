# -*- coding: utf-8 -*-
"""
GUI-тест POST /parse (Tkinter).

Запуск:
    python test_parse_gui.py

Подхватывает APP_API_KEY из .env в корне проекта.
Можно указать файл(ы) сразу:
    python test_parse_gui.py path\\to\\file.pdf
"""

from __future__ import print_function

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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


def main():
    _load_dotenv()
    # Prefer local API URL for parse tests.
    if not os.environ.get("BASE_URL") and not os.environ.get("API_BASE_URL"):
        host = os.environ.get("HOST", "127.0.0.1")
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"
        port = os.environ.get("PORT", "8000")
        default_url = "http://{}:{}/parse".format(host, port)
    else:
        base = (os.environ.get("BASE_URL") or os.environ.get("API_BASE_URL")).rstrip("/")
        default_url = "{}/parse".format(base)

    from utils.gui_client import ParseClientApp, DEFAULT_URL
    import tkinter as tk
    from tkinter import ttk

    # Patch module default if still stock.
    import utils.gui_client as gui

    if gui.DEFAULT_URL == DEFAULT_URL:
        gui.DEFAULT_URL = default_url

    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass

    app = ParseClientApp(root)
    app.url_var.set(default_url)
    key = (os.environ.get("APP_API_KEY") or "").strip()
    if key:
        app.api_key_var.set(key)

    # Optional CLI file paths pre-selected in the list.
    for arg in sys.argv[1:]:
        path = str(Path(arg).expanduser().resolve())
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".pdf", ".docx"):
            print("Skip (not pdf/docx):", path)
            continue
        if not os.path.isfile(path):
            print("Skip (missing):", path)
            continue
        if path not in app.file_paths:
            app.file_paths.append(path)
            app.files_list.insert(tk.END, path)

    root.mainloop()


if __name__ == "__main__":
    main()
