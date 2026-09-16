"""Normalize multipart upload filenames (Delphi/Indy RFC 2047, etc.)."""

from email.header import decode_header
from pathlib import Path
from typing import Optional

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


def decode_upload_filename(name):
    # type: (Optional[str]) -> str
    """
    Decode MIME encoded-word filenames, e.g.
    =?KOI8-R?B?...?= → readable Cyrillic name with .pdf/.docx
    """
    raw = (name or "").strip() or "unnamed"
    if "=?" not in raw or "?=" not in raw:
        return raw
    try:
        chunks = []
        for data, charset in decode_header(raw):
            if isinstance(data, bytes):
                chunks.append(
                    data.decode(charset or "utf-8", errors="replace")
                )
            else:
                chunks.append(data)
        decoded = "".join(chunks).strip()
        return decoded or raw
    except Exception:
        return raw


def extension_from_content_type(content_type):
    # type: (Optional[str]) -> str
    ctype = (content_type or "").lower()
    if "pdf" in ctype:
        return ".pdf"
    if "wordprocessingml" in ctype or "officedocument" in ctype:
        return ".docx"
    return ""


def sniff_extension(path):
    # type: (Path) -> str
    try:
        head = path.read_bytes()[:8]
    except OSError:
        return ""
    if head.startswith(b"%PDF"):
        return ".pdf"
    if head.startswith(b"PK"):
        return ".docx"
    return ""


def resolve_upload_extension(filename, content_type, path=None):
    # type: (str, Optional[str], Optional[Path]) -> str
    """Pick .pdf / .docx from name, Content-Type, or file magic."""
    ext = Path(filename).suffix.lower()
    if ext in SUPPORTED_EXTENSIONS:
        return ext
    from_mime = extension_from_content_type(content_type)
    if from_mime in SUPPORTED_EXTENSIONS:
        return from_mime
    if path is not None:
        sniffed = sniff_extension(path)
        if sniffed in SUPPORTED_EXTENSIONS:
            return sniffed
    return ext
