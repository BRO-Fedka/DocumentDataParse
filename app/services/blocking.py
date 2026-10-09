"""Pack document atoms into GPT-sized text blocks using current JSON state."""

from typing import List, Optional

from loguru import logger

from app.config import Settings
from app.services.yandex_gpt import measure_request_chars


def _table_header(lines):
    # type: (List[str]) -> Optional[str]
    """First row of a docx table atom (cells joined with ' | ')."""
    if len(lines) >= 2 and " | " in lines[0]:
        return lines[0]
    return None


def split_atom_chunks(atom, max_doc_chars):
    # type: (str, int) -> List[str]
    """
    Split one atom into pieces of at most max_doc_chars.
    Table atoms keep the header row at the start of every piece.
    """
    text = (atom or "").strip()
    if not text:
        return []
    limit = int(max_doc_chars or 0)
    if limit <= 0 or len(text) <= limit:
        return [text]

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return [text]

    header = _table_header(lines)
    body = lines[1:] if header else lines
    overhead = (len(header) + 1) if header else 0
    budget = limit - overhead
    if budget < 1:
        logger.warning(
            "Table header is longer than the block limit ({} > {}); "
            "splitting without repeating it",
            len(header or ""),
            limit,
        )
        header = None
        body = lines
        budget = limit

    chunks = []  # type: List[str]
    current = []  # type: List[str]
    current_len = 0

    def flush():
        # type: () -> None
        nonlocal current_len
        if not current:
            return
        parts = []
        if header:
            parts.append(header)
        parts.extend(current)
        chunks.append("\n".join(parts))
        current.clear()
        current_len = 0

    for line in body:
        if len(line) > budget:
            flush()
            for offset in range(0, len(line), budget):
                piece = line[offset : offset + budget]
                if header:
                    chunks.append(header + "\n" + piece)
                else:
                    chunks.append(piece)
            continue
        extra = len(line) if not current else (1 + len(line))
        if current and current_len + extra > budget:
            flush()
            extra = len(line)
        current.append(line)
        current_len += extra
    flush()
    return chunks or [text[:limit]]


def arrange_atoms(atoms, prompt, state, settings):
    # type: (List[str], str, dict, Settings) -> tuple
    """
    Atoms that cannot fit in one GPT request (max_input_chars) are deferred.
    Smaller atoms that exceed the block cap are split in place, in order.
    Returns (primary, deferred).
    """
    max_doc = int(getattr(settings, "gpt_max_block_doc_chars", 0) or 0)
    primary = []  # type: List[str]
    deferred = []  # type: List[str]
    for atom in atoms:
        text = (atom or "").strip()
        if not text:
            continue
        request_chars = measure_request_chars(prompt, state, text, settings)
        if request_chars > settings.max_input_chars:
            deferred.append(text)
            logger.info(
                "Deferred oversized atom doc_chars={} request_chars={} limit={}",
                len(text),
                request_chars,
                settings.max_input_chars,
            )
            continue
        if max_doc and len(text) > max_doc:
            primary.extend(split_atom_chunks(text, max_doc))
        else:
            primary.append(text)
    return primary, deferred


def take_next_block(atoms, prompt, state, settings):
    # type: (List[str], str, dict, Settings) -> Optional[str]
    """
    Build one block from the front of `atoms` using the *current* state size.

    Atoms that fit are popped from `atoms`. Returns block text, or None if
    `atoms` is empty.
    """
    if not atoms:
        return None

    max_chars = settings.max_input_chars
    max_doc_chars = int(getattr(settings, "gpt_max_block_doc_chars", 0) or 0)
    current_parts = []  # type: List[str]

    while atoms:
        candidate_parts = current_parts + [atoms[0]]
        candidate = "\n".join(candidate_parts)
        size = measure_request_chars(prompt, state, candidate, settings)
        doc_too_big = bool(max_doc_chars) and len(candidate) > max_doc_chars

        if not current_parts:
            if size > max_chars:
                raise ValueError(
                    "Single document atom exceeds GPT input limit "
                    "({} > {} chars) with current JSON state".format(size, max_chars)
                )
            # Oversized single atom: still send alone (cannot split further here).
            current_parts.append(atoms.pop(0))
            if doc_too_big and max_doc_chars:
                logger.warning(
                    "Single atom exceeds GPT_MAX_BLOCK_DOC_CHARS "
                    "({} > {}); sending alone",
                    len(candidate),
                    max_doc_chars,
                )
            continue

        if size <= max_chars and not doc_too_big:
            current_parts.append(atoms.pop(0))
        else:
            break

    block = "\n".join(current_parts)
    logger.info(
        "Built block atoms={} doc_chars={} request_chars={} "
        "budget={} max_doc={} remaining_atoms={}",
        len(current_parts),
        len(block),
        measure_request_chars(prompt, state, block, settings),
        max_chars,
        max_doc_chars or "off",
        len(atoms),
    )
    return block
