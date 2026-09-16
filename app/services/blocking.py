"""Pack document atoms into GPT-sized text blocks using current JSON state."""

from typing import List, Optional

from loguru import logger

from app.config import Settings
from app.services.yandex_gpt import measure_request_chars


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
