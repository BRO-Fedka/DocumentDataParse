"""DocumentDataParse Flask application factory."""

from flask import Flask, jsonify
from loguru import logger
from werkzeug.exceptions import HTTPException

from app.config import get_settings
from app.logging_setup import setup_logging
from app.routes.parse import bp as parse_bp


def create_app():
    # type: () -> Flask
    settings = get_settings()
    setup_logging(settings)
    settings.temp_dir_path.mkdir(parents=True, exist_ok=True)
    settings.log_dir_path.mkdir(parents=True, exist_ok=True)

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_bytes
    app.register_blueprint(parse_bp)

    @app.errorhandler(Exception)
    def _unhandled_error(exc):
        # Keep normal HTTP errors (404/401/…) as-is.
        if isinstance(exc, HTTPException):
            return exc
        logger.exception("Unhandled Flask exception: {}", exc)
        return jsonify({"detail": "Internal server error"}), 500

    return app
