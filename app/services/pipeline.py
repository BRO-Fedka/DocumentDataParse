import time
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from loguru import logger
from werkzeug.datastructures import FileStorage

from app.config import Settings
from app.models import FileParseResult, FileResultMeta
from app.services.blocking import take_next_block
from app.services.docx_extract import extract_docx_atoms
from app.services.pdf_extract import analyze_pdf, extract_pdf_page_atoms
from app.services.schema_state import (
    apply_gpt_state,
    extract_skeleton,
    fresh_state,
    is_state_complete,
)
from app.validators import validate_json_structure
from app.services.vision import extract_pdf_atoms_with_vision
from app.services.yandex_gpt import YandexGptError, extract_fields_with_gpt

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


def _is_content_filter_error(exc):
    # type: (BaseException) -> bool
    text = str(exc).lower()
    return "не могу обсуждать" in text or '"code":3' in text or "code': 3" in text

# TODO(later): strict MIME / content-type validation for uploads.


def safe_unlink(path):
    # type: (Path) -> None
    try:
        if path.exists():
            path.unlink()
    except OSError as exc:
        logger.warning("Failed to delete temp file {}: {}", path, exc)


def save_upload(upload, dest, max_bytes):
    # type: (FileStorage, Path, int) -> int
    size = 0
    stream = upload.stream
    with dest.open("wb") as out:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("File exceeds MAX_UPLOAD_BYTES ({})".format(max_bytes))
            out.write(chunk)
    return size


def _collect_atoms(path, ext, settings):
    # type: (Path, str, Settings) -> Tuple[List[str], Optional[str], Optional[int]]
    text_source = None  # type: Optional[str]
    page_count = None  # type: Optional[int]

    if ext == ".docx":
        atoms = extract_docx_atoms(path)
        text_source = "docx"
        return atoms, text_source, page_count

    analysis = analyze_pdf(path, settings)
    page_count = analysis.page_count
    if page_count > settings.max_pages:
        raise ValueError(
            "PDF has {} pages; MAX_PAGES={}".format(page_count, settings.max_pages)
        )
    if analysis.use_vision:
        # Whole PDF -> Vision once -> paragraph-like atoms (same GPT path as DOCX).
        atoms = extract_pdf_atoms_with_vision(path, settings)
        text_source = "vision:{}".format(analysis.reason)
    else:
        atoms = extract_pdf_page_atoms(path)
        text_source = "pdf_text:{}".format(analysis.reason)
    return atoms, text_source, page_count


def _process_block_with_retries(block_text, settings, prompt, state):
    # type: (str, Settings, str, dict) -> Tuple[dict, int]
    """Try GPT on one block up to GPT_BLOCK_RETRIES (N)."""
    last_error = None  # type: Optional[Exception]
    attempts = 0
    for attempt in range(1, settings.gpt_block_retries + 1):
        attempts = attempt
        try:
            # Work on a copy until merge succeeds.
            trial_state = fresh_state(state)
            raw = extract_fields_with_gpt(block_text, settings, prompt, trial_state)
            raw = validate_json_structure(raw)
            apply_gpt_state(
                trial_state, raw, allow_overwrite=settings.merge_allow_overwrite
            )
            # Commit into caller's state object.
            state.clear()
            state.update(trial_state)
            return state, attempts
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Block GPT attempt {}/{} failed: {}",
                attempt,
                settings.gpt_block_retries,
                exc,
            )
            # Content filter will not change on retry — stop early.
            if isinstance(exc, YandexGptError) and _is_content_filter_error(exc):
                break
    raise RuntimeError(
        "Block analysis failed after {} attempts: {}".format(attempts, last_error)
    )


def _run_analysis(atoms, settings, prompt, skeleton):
    # type: (List[str], Settings, str, dict) -> Tuple[dict, int, int]
    """
    Full pass over document atoms. Each next block is packed with the *current*
    JSON state size. Retries whole analysis up to GPT_ANALYSIS_RETRIES (M).

    Returns final state, total GPT attempts, and number of blocks sent.
    """
    last_error = None  # type: Optional[Exception]
    total_attempts = 0
    cleaned = [atom.strip() for atom in atoms if atom and atom.strip()]

    for analysis_round in range(1, settings.gpt_analysis_retries + 1):
        state = fresh_state(skeleton)
        remaining = list(cleaned)
        blocks_sent = 0
        try:
            logger.info(
                "Analysis round {}/{} atoms={}",
                analysis_round,
                settings.gpt_analysis_retries,
                len(remaining),
            )
            while remaining:
                # Pack next block against the current (possibly filled) JSON.
                block_text = take_next_block(remaining, prompt, state, settings)
                if not block_text:
                    break
                blocks_sent += 1
                logger.info(
                    "Processing block {} (remaining_atoms={})",
                    blocks_sent,
                    len(remaining),
                )
                try:
                    state, attempts = _process_block_with_retries(
                        block_text, settings, prompt, state
                    )
                    total_attempts += attempts
                except RuntimeError as exc:
                    # Keep partial progress: skip poisoned/filtered blocks.
                    total_attempts += settings.gpt_block_retries
                    logger.warning(
                        "Skipping block {} after failures: {}",
                        blocks_sent,
                        exc,
                    )
                    continue
                if is_state_complete(state):
                    logger.info(
                        "All fields filled after block {}; "
                        "skipping remaining_atoms={}",
                        blocks_sent,
                        len(remaining),
                    )
                    break
            return state, total_attempts, blocks_sent
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Analysis round {}/{} failed: {}",
                analysis_round,
                settings.gpt_analysis_retries,
                exc,
            )

    raise RuntimeError(
        "Document analysis failed after {} full restarts: {}".format(
            settings.gpt_analysis_retries, last_error
        )
    )


def process_local_file(path, filename, content_type, size_bytes, settings, prompt):
    # type: (Path, str, Optional[str], int, Settings, str) -> FileParseResult
    started = time.perf_counter()
    ext = path.suffix.lower()
    text_source = None  # type: Optional[str]
    page_count = None  # type: Optional[int]
    gpt_attempts = None  # type: Optional[int]

    try:
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError("Unsupported extension: {}".format(ext))

        skeleton = extract_skeleton(prompt)
        atoms, text_source, page_count = _collect_atoms(path, ext, settings)
        if not any(atom.strip() for atom in atoms):
            raise ValueError("Extracted text is empty")

        fields, gpt_attempts, blocks_sent = _run_analysis(
            atoms, settings, prompt, skeleton
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "Parsed file ok filename={} size={} type={} source={} pages={} "
            "blocks={} gpt_attempts={} duration_ms={}",
            filename,
            size_bytes,
            content_type,
            text_source,
            page_count,
            blocks_sent,
            gpt_attempts,
            duration_ms,
        )
        return FileParseResult(
            filename=filename,
            success=True,
            fields=fields,
            meta=FileResultMeta(
                size_bytes=size_bytes,
                content_type=content_type,
                extension=ext,
                text_source=text_source,
                page_count=page_count,
                gpt_attempts=gpt_attempts,
                duration_ms=duration_ms,
            ),
        )
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.exception(
            "Failed to parse file filename={} size={} type={} duration_ms={} error={}",
            filename,
            size_bytes,
            content_type,
            duration_ms,
            exc,
        )
        return FileParseResult(
            filename=filename,
            success=False,
            fields=None,
            meta=FileResultMeta(
                size_bytes=size_bytes,
                content_type=content_type,
                extension=ext or Path(filename).suffix.lower(),
                text_source=text_source,
                page_count=page_count,
                gpt_attempts=gpt_attempts,
                duration_ms=duration_ms,
                error=str(exc),
            ),
        )


def process_uploads(files, username, request_id, settings, prompt):
    # type: (List[FileStorage], str, str, Settings, str) -> List[FileParseResult]
    settings.temp_dir_path.mkdir(parents=True, exist_ok=True)
    results = []  # type: List[FileParseResult]

    logger.info(
        "Parse request start request_id={} username={} files_count={}",
        request_id,
        username,
        len(files),
    )

    for upload in files:
        original_name = upload.filename or "unnamed"
        ext = Path(original_name).suffix.lower()
        temp_path = settings.temp_dir_path / "{}_{}{}".format(
            request_id, uuid.uuid4().hex, ext
        )
        size_bytes = 0
        try:
            size_bytes = save_upload(upload, temp_path, settings.max_upload_bytes)
            result = process_local_file(
                temp_path,
                filename=original_name,
                content_type=upload.mimetype,
                size_bytes=size_bytes,
                settings=settings,
                prompt=prompt,
            )
            results.append(result)
        except Exception as exc:
            logger.exception(
                "Upload handling failed request_id={} username={} filename={} error={}",
                request_id,
                username,
                original_name,
                exc,
            )
            results.append(
                FileParseResult(
                    filename=original_name,
                    success=False,
                    fields=None,
                    meta=FileResultMeta(
                        size_bytes=size_bytes,
                        content_type=upload.mimetype,
                        extension=ext,
                        error=str(exc),
                    ),
                )
            )
        finally:
            safe_unlink(temp_path)

    logger.info(
        "Parse request finish request_id={} username={} ok={} failed={}",
        request_id,
        username,
        sum(1 for r in results if r.success),
        sum(1 for r in results if not r.success),
    )
    return results
