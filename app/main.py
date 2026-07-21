"""Run: python -m app.main  or  flask --app app.main:app run"""

from app import create_app
from app.config import get_settings

app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    app.run(host=settings.host, port=settings.port, debug=settings.debug)
