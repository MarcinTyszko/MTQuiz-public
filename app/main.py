"""Punkt wejścia aplikacji FastAPI — montowanie routerów i obsługa błędów."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .bootstrap import initialise
from .config import STATIC_DIR, settings
from .routers import admin, auth, pages, sets, study
from .templating import templates

logger = logging.getLogger("mtquiz")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialise()
    logger.info("Baza danych: %s", settings.database_path)
    yield


app = FastAPI(
    title=settings.app_name,
    description="Samohostowana platforma nauki: fiszki i quizy dla kierunków medycznych.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(auth.router)
app.include_router(sets.router)
app.include_router(study.router)
app.include_router(admin.router)
app.include_router(pages.router)


def _wants_html(request: Request) -> bool:
    """Rozstrzyga, czy błąd ma być stroną HTML, czy odpowiedzią JSON."""
    if request.url.path.startswith("/api/"):
        return False
    accept = request.headers.get("accept", "")
    # Odpowiedź JSON wyłącznie wtedy, gdy klient wprost o nią prosi.
    if "application/json" in accept and "text/html" not in accept:
        return False
    return True


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Zwraca JSON dla API, a przyjazną stronę błędu dla widoków HTML."""
    if _wants_html(request):
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return RedirectResponse(url=f"/logowanie?next={request.url.path}", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse(
            request,
            "error.html",
            {"status_code": exc.status_code, "detail": exc.detail},
            status_code=exc.status_code,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Tłumaczy błędy walidacji Pydantica na czytelny komunikat po polsku."""
    messages: list[str] = []
    details: list[dict[str, str]] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()) if part not in ("body", "query"))
        message = str(error.get("msg", "Nieprawidłowa wartość."))
        messages.append(f"{location}: {message}" if location else message)
        # Pole ``ctx`` bywa obiektem wyjątku, dlatego przepisujemy tylko dane proste.
        details.append({"path": location, "message": message, "type": str(error.get("type", ""))})

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Dane formularza są nieprawidłowe: " + "; ".join(messages[:6]),
            "errors": details[:20],
        },
    )


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    """Sonda zdrowia dla Dockera i monitoringu."""
    return {"status": "ok", "app": settings.app_name}
