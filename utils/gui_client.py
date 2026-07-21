"""
Simple GUI client for DocumentDataParse API.

Run (API must be up):
    python utils/gui_client.py
"""

from __future__ import print_function

import json
import mimetypes
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    import requests
except ImportError:
    raise SystemExit("Install requests: pip install requests")


DEFAULT_URL = "http://127.0.0.1:8000/parse"
FILETYPES = [
    ("Documents", "*.pdf *.docx"),
    ("PDF", "*.pdf"),
    ("Word DOCX", "*.docx"),
    ("All files", "*.*"),
]

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Display name -> prompt filename in project root
DOC_TYPES = [
    ("Договор", "Prompt.txt"),
    ("Доп.соглашение", "Prompt_dop.txt"),
    ("Акт выполненных работ", "Prompt_akt.txt"),
]
DEFAULT_DOC_TYPE = "Договор"


def _prompt_path(filename):
    # type: (str) -> str
    return os.path.join(_ROOT, filename)


def _load_prompt_file(filename):
    # type: (str) -> str
    path = _prompt_path(filename)
    if not os.path.isfile(path):
        raise IOError("Prompt file not found: {}".format(path))
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _filename_for_doc_type(doc_type):
    # type: (str) -> str
    for name, filename in DOC_TYPES:
        if name == doc_type:
            return filename
    return DOC_TYPES[0][1]


class ParseClientApp(object):
    def __init__(self, root):
        # type: (tk.Tk) -> None
        self.root = root
        self.root.title("DocumentDataParse — test client")
        self.root.geometry("860x760")
        self.root.minsize(700, 580)

        self.file_paths = []  # type: list
        self._busy = False
        self._loading_prompt = False

        self._build_ui()
        self._load_prompt_for_type(DEFAULT_DOC_TYPE)

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        row = 0
        ttk.Label(frm, text="API URL").grid(row=row, column=0, sticky=tk.W, **pad)
        self.url_var = tk.StringVar(value=DEFAULT_URL)
        ttk.Entry(frm, textvariable=self.url_var).grid(
            row=row, column=1, columnspan=2, sticky=tk.EW, **pad
        )

        row += 1
        ttk.Label(frm, text="API key").grid(row=row, column=0, sticky=tk.W, **pad)
        self.api_key_var = tk.StringVar(value=os.environ.get("APP_API_KEY", ""))
        ttk.Entry(frm, textvariable=self.api_key_var, show="*").grid(
            row=row, column=1, columnspan=2, sticky=tk.EW, **pad
        )

        row += 1
        ttk.Label(frm, text="Username").grid(row=row, column=0, sticky=tk.W, **pad)
        self.username_var = tk.StringVar(value="gui-tester")
        ttk.Entry(frm, textvariable=self.username_var).grid(
            row=row, column=1, columnspan=2, sticky=tk.EW, **pad
        )

        row += 1
        ttk.Label(frm, text="Тип документа").grid(row=row, column=0, sticky=tk.W, **pad)
        self.doc_type_var = tk.StringVar(value=DEFAULT_DOC_TYPE)
        self.doc_type_combo = ttk.Combobox(
            frm,
            textvariable=self.doc_type_var,
            values=[name for name, _ in DOC_TYPES],
            state="readonly",
        )
        self.doc_type_combo.grid(row=row, column=1, columnspan=2, sticky=tk.EW, **pad)
        self.doc_type_combo.bind("<<ComboboxSelected>>", self._on_doc_type_changed)

        row += 1
        ttk.Label(frm, text="Prompt").grid(row=row, column=0, sticky=tk.NW, **pad)
        self.prompt_box = scrolledtext.ScrolledText(frm, wrap=tk.WORD, height=12)
        self.prompt_box.grid(row=row, column=1, columnspan=2, sticky=tk.NSEW, **pad)
        self._prompt_row = row

        row += 1
        ttk.Label(frm, text="Files").grid(row=row, column=0, sticky=tk.NW, **pad)
        self.files_list = tk.Listbox(frm, height=4, selectmode=tk.EXTENDED)
        self.files_list.grid(row=row, column=1, sticky=tk.NSEW, **pad)

        btn_col = ttk.Frame(frm)
        btn_col.grid(row=row, column=2, sticky=tk.N, **pad)
        ttk.Button(btn_col, text="Add…", command=self.add_files).pack(fill=tk.X, pady=2)
        ttk.Button(btn_col, text="Remove", command=self.remove_selected).pack(
            fill=tk.X, pady=2
        )
        ttk.Button(btn_col, text="Clear", command=self.clear_files).pack(
            fill=tk.X, pady=2
        )
        self._files_row = row

        row += 1
        self.send_btn = ttk.Button(frm, text="Send to API", command=self.send)
        self.send_btn.grid(row=row, column=0, columnspan=3, sticky=tk.EW, padx=8, pady=8)

        row += 1
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(frm, textvariable=self.status_var).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, **pad
        )

        row += 1
        ttk.Label(frm, text="Response JSON").grid(
            row=row, column=0, columnspan=3, sticky=tk.W, **pad
        )

        row += 1
        self.output = scrolledtext.ScrolledText(frm, wrap=tk.WORD, height=14)
        self.output.grid(row=row, column=0, columnspan=3, sticky=tk.NSEW, **pad)
        self._output_row = row

        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(self._prompt_row, weight=1)
        frm.rowconfigure(self._output_row, weight=2)

    def _on_doc_type_changed(self, _event=None):
        self._load_prompt_for_type(self.doc_type_var.get())

    def _load_prompt_for_type(self, doc_type):
        # type: (str) -> None
        filename = _filename_for_doc_type(doc_type)
        try:
            text = _load_prompt_file(filename)
        except IOError as exc:
            messagebox.showerror("Prompt", str(exc))
            return
        self._loading_prompt = True
        self.prompt_box.delete("1.0", tk.END)
        self.prompt_box.insert(tk.END, text)
        self._loading_prompt = False
        self.status_var.set("Loaded {} ({})".format(doc_type, filename))

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select PDF / DOCX",
            filetypes=FILETYPES,
        )
        for path in paths:
            ext = os.path.splitext(path)[1].lower()
            if ext not in (".pdf", ".docx"):
                messagebox.showwarning(
                    "Unsupported",
                    "Skipped (only .pdf / .docx): {}".format(os.path.basename(path)),
                )
                continue
            if path not in self.file_paths:
                self.file_paths.append(path)
                self.files_list.insert(tk.END, path)

    def remove_selected(self):
        selection = list(self.files_list.curselection())
        selection.reverse()
        for index in selection:
            self.files_list.delete(index)
            del self.file_paths[index]

    def clear_files(self):
        self.file_paths = []
        self.files_list.delete(0, tk.END)

    def send(self):
        if self._busy:
            return

        url = self.url_var.get().strip()
        api_key = self.api_key_var.get().strip()
        username = self.username_var.get().strip()
        prompt = self.prompt_box.get("1.0", tk.END).strip()

        if not url:
            messagebox.showerror("Error", "API URL is required")
            return
        if not api_key:
            messagebox.showerror("Error", "API key is required")
            return
        if not username:
            messagebox.showerror("Error", "Username is required")
            return
        if not prompt:
            messagebox.showerror("Error", "Prompt is required")
            return
        if not self.file_paths:
            messagebox.showerror("Error", "Select at least one PDF/DOCX file")
            return

        self._busy = True
        self.send_btn.config(state=tk.DISABLED)
        self.status_var.set("Sending… ({})".format(self.doc_type_var.get()))
        self.output.delete("1.0", tk.END)

        thread = threading.Thread(
            target=self._request_worker,
            args=(url, api_key, username, prompt, list(self.file_paths)),
            daemon=True,
        )
        thread.start()

    def _request_worker(self, url, api_key, username, prompt, paths):
        # type: (str, str, str, str, list) -> None
        opened = []
        try:
            files = []
            for path in paths:
                handle = open(path, "rb")
                opened.append(handle)
                mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
                files.append(("files", (os.path.basename(path), handle, mime)))

            response = requests.post(
                url,
                headers={"X-API-Key": api_key},
                data={"username": username, "prompt": prompt},
                files=files,
                timeout=600,
            )
            try:
                payload = response.json()
                text = json.dumps(payload, ensure_ascii=False, indent=2)
            except ValueError:
                text = response.text

            self.root.after(
                0,
                self._show_result,
                response.status_code,
                text,
            )
        except Exception as exc:
            self.root.after(0, self._show_error, str(exc))
        finally:
            for handle in opened:
                try:
                    handle.close()
                except Exception:
                    pass

    def _show_result(self, status_code, text):
        # type: (int, str) -> None
        self.output.insert(tk.END, text)
        self.status_var.set("HTTP {}".format(status_code))
        self._busy = False
        self.send_btn.config(state=tk.NORMAL)

    def _show_error(self, message):
        # type: (str) -> None
        self.output.insert(tk.END, "Request failed:\n{}".format(message))
        self.status_var.set("Error")
        self._busy = False
        self.send_btn.config(state=tk.NORMAL)
        messagebox.showerror("Request failed", message)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    ParseClientApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
