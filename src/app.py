from fastapi import FastAPI

from src.envelope.routes import router as envelope_router

app = FastAPI(title="Envelope API")
app.include_router(envelope_router)
