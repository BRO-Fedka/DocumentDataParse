"""Run: python -m app.main  or  flask --app app.main:app run"""

from app import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
