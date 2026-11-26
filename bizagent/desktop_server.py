from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.main import app

app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "frontend", html=True), name="frontend")
