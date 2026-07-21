from flask import Request

from app.config import get_settings


def check_api_key(request):
    # type: (Request) -> bool
    """Return True if X-API-Key header matches APP_API_KEY."""
    settings = get_settings()
    provided = request.headers.get("X-API-Key")
    return bool(provided) and provided == settings.app_api_key
