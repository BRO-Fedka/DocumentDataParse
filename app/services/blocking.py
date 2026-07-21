"""Pack document atoms into GPT-sized text blocks."""

from typing import List

from loguru import logger

from app.config import Settings
from app.services.schema_state import state_to_json
from app.services.yandex_gpt import SYSTEM_PROMPT, build_user_message


def pack_atoms_into_blocks(atoms, prompt, state, settings):
    # type: (List[str], str, dict, Settings) -> List[str]
    """
    Greedy pack: append atom to current block while full request fits max_input_chars.
    If atom does not fit into current block, start a new block with that atom.
    """
    max_chars = settings.max_input_chars
    state_json = state_to_json(state)
    cleaned = [atom.strip() for atom in atoms if atom and atom.strip()]
    if not cleaned:
        return []

    def fits(block_text):
        # type: (str) -> bool
        user = build_user_message(prompt, state_json, block_text)
        total = len(SYSTEM_PROMPT) + len(user)
        return total <= max_chars

    blocks = []  # type: List[str]
    current_parts = []  # type: List[str]

    for atom in cleaned:
        candidate_parts = current_parts + [atom]
        candidate = "\n".join(candidate_parts)
        if not current_parts:
            if not fits(candidate):
                raise ValueError(
                    "Single document atom exceeds GPT input limit "
                    "({} chars budget)".format(max_chars)
                )
            current_parts = candidate_parts
            continue

        if fits(candidate):
            current_parts = candidate_parts
        else:
            blocks.append("\n".join(current_parts))
            if not fits(atom):
                raise ValueError(
                    "Single document atom exceeds GPT input limit "
                    "({} chars budget)".format(max_chars)
                )
            current_parts = [atom]

    if current_parts:
        blocks.append("\n".join(current_parts))

    logger.info(
        "Packed {} atoms into {} GPT blocks (budget_chars={})",
        len(cleaned),
        len(blocks),
        max_chars,
    )
    return blocks
