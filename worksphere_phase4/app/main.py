from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine
from . import models  # noqa: F401  (register tables)
from .routers import announcements, auth, feedback, integrations, onboarding, profile, resignations, tasks

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="WorkSphere HRMS - Phase 4", version="4.0.0", lifespan=lifespan)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/app"):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'",
        )
    return response


for module in (auth, onboarding, resignations, announcements, tasks, integrations, feedback, profile):
    app.include_router(module.router)


@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/app/")


app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
