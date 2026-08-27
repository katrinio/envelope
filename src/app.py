from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from src.envelope.routes import router as envelope_router

SRC_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Envelope API")


@app.middleware("http")
async def add_cache_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("text/html"):
        # Entry documents must be revalidated so deployments are discovered
        # on an ordinary reload.
        response.headers["Cache-Control"] = "no-cache"
    elif request.url.path.startswith("/static/"):
        if request.url.query:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/static", StaticFiles(directory=SRC_DIR / "static"), name="static")
app.include_router(envelope_router)
