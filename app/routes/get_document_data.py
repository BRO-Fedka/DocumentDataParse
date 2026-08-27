import uuid

from flask import Blueprint, jsonify, request
from loguru import logger

from app.auth import check_api_key
from app.config import get_settings
from app.models import ParseResponse
from app.services.pipeline import process_document_text
from app.services.zakupki import ZakupkiLookupError, fetch_zakupki_print_atoms

bp = Blueprint("get_document_data", __name__)


@bp.route("/get_document_data", methods=["POST"])
def get_document_data():
    if not check_api_key(request):
        return jsonify({"detail": "Invalid or missing API key"}), 401

    username = (request.form.get("username") or "").strip()
    if not username:
        return jsonify({"detail": "username is required"}), 400

    prompt = (request.form.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"detail": "prompt is required"}), 400

    document_id = (request.form.get("document_id") or "").strip()
    if not document_id:
        return jsonify({"detail": "document_id is required"}), 400

    settings = get_settings()
    request_id = str(uuid.uuid4())
    logger.info(
        "Incoming /get_document_data request_id={} username={} document_id={} "
        "prompt_chars={}",
        request_id,
        username,
        document_id,
        len(prompt),
    )

    try:
        atoms, print_url, search_url = fetch_zakupki_print_atoms(
            document_id, settings
        )
    except ZakupkiLookupError as exc:
        logger.warning(
            "Zakupki lookup failed request_id={} document_id={} detail={}",
            request_id,
            document_id,
            exc,
        )
        return jsonify({"detail": str(exc)}), 400
    except Exception as exc:
        logger.exception(
            "Zakupki fetch failed request_id={} document_id={} error={}",
            request_id,
            document_id,
            exc,
        )
        # Surface root cause (often SSLCertVerificationError behind MITM/proxy).
        return (
            jsonify(
                {
                    "detail": "Failed to fetch document from zakupki.gov.ru: {}".format(
                        exc
                    )
                }
            ),
            502,
        )

    size_bytes = sum(len(atom.encode("utf-8")) for atom in atoms)
    result = process_document_text(
        atoms,
        filename="zakupki:{}".format(document_id),
        settings=settings,
        prompt=prompt,
        text_source="zakupki_print:{}".format(print_url),
        content_type="text/html",
        size_bytes=size_bytes,
        extension=".html",
        page_count=None,
    )
    logger.info(
        "Zakupki parse done request_id={} document_id={} search_url={} "
        "print_url={} success={}",
        request_id,
        document_id,
        search_url,
        print_url,
        result.success,
    )

    payload = ParseResponse(
        request_id=request_id,
        username=username,
        results=[result],
    )
    return jsonify(payload.to_dict()), 200
