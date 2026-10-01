import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from surveyor.api import router
from surveyor.bootstrap import bootstrap
from surveyor.config import settings
from surveyor.db import engine
from surveyor.document_api import router as document_router
from surveyor.source_api import router as source_router
from surveyor.telegram import router as telegram_router

STATIC = Path(__file__).parent / "static"
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app):
    bootstrap()
    yield


app = FastAPI(
    title="Surveyor API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)
app.include_router(router)

app.include_router(source_router)
app.include_router(document_router)
app.include_router(telegram_router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def security(request: Request, call_next):
    origin = request.headers.get("origin")
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and origin
        and origin.rstrip("/") != settings.public_url.rstrip("/")
    ):
        return JSONResponse({"detail": "Недопустимый источник запроса"}, status_code=403)
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > settings.max_upload_bytes + 65536):
        return JSONResponse({"detail": "Слишком большой запрос"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = (
        "no-store" if request.url.path.startswith(("/api", "/telegram")) else "no-cache"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self' https://web.telegram.org https://*.telegram.org; base-uri 'self'; form-action 'self'"
    )
    return response


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({"detail": str(exc)[:1500]}, status_code=422)


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(
        {"detail": "Такая запись уже существует (логин, телефон, Telegram ID или версия)"}, status_code=409
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Pydantic's default response can echo input, including passwords.
    return JSONResponse(
        {"detail": "; ".join(f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors())},
        status_code=422,
    )


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "ai_enabled": False, "data_mode": settings.data_mode}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
