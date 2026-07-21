import uuid

from flask import Blueprint, jsonify, request
from loguru import logger

from app.auth import check_api_key
from app.config import get_settings
from app.models import ParseResponse
from app.services.pipeline import process_uploads

bp = Blueprint("parse", __name__)


@bp.route("/parse", methods=["POST"])
def parse_documents():
    if not check_api_key(request):
        return jsonify({"detail": "Invalid or missing API key"}), 401

    username = (request.form.get("username") or "").strip()
    if not username:
        return jsonify({"detail": "username is required"}), 400

    prompt = (request.form.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"detail": "prompt is required"}), 400

    files = request.files.getlist("files")
    if not files or all(not f.filename for f in files):
        return jsonify({"detail": "At least one file is required"}), 400

    settings = get_settings()
    request_id = str(uuid.uuid4())
    logger.info(
        "Incoming /parse request_id={} username={} files={} prompt_chars={}",
        request_id,
        username,
        [f.filename for f in files],
        len(prompt),
    )

    results = process_uploads(
        files,
        username=username,
        request_id=request_id,
        settings=settings,
        prompt=prompt,
    )
    payload = ParseResponse(
        request_id=request_id,
        username=username,
        results=results,
    )
    return jsonify(payload.to_dict()), 200
