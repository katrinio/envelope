from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.envelope.routes import router as envelope_router

SRC_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Envelope API")
app.mount("/static", StaticFiles(directory=SRC_DIR / "static"), name="static")
app.include_router(envelope_router)
