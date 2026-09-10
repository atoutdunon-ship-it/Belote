"""Team Belote & Re - point d'entree ASGI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .api import api, hub
from .config import get_settings
from .db import SessionLocal, init_db
from .models import Player
from .security import hash_pin

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def bootstrap_admin() -> None:
    settings = get_settings()
    with SessionLocal() as session:
        exists = session.execute(select(Player).limit(1)).scalar_one_or_none()
        if exists is not None:
            return
        session.add(
            Player(
                numero=settings.admin_numero,
                nom=settings.admin_nom,
                pin_hash=hash_pin(settings.admin_pin),
                is_admin=True,
            )
        )
        session.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    bootstrap_admin()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api)


@app.get("/api/health", tags=["systeme"])
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.websocket("/ws/tournaments/{tournament_id}")
async def tournament_feed(websocket: WebSocket, tournament_id: int) -> None:
    await hub.join(tournament_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.leave(tournament_id, websocket)


if WEB_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/service-worker.js", include_in_schema=False)
    def service_worker() -> FileResponse:
        return FileResponse(WEB_DIR / "service-worker.js", media_type="application/javascript")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    # Les liens de l'interface sont relatifs afin de fonctionner aussi sous
    # GitHub Pages. Ce second montage les rend disponibles a la racine avec
    # FastAPI, sans intercepter les routes API definies precedemment.
    app.mount("/", StaticFiles(directory=WEB_DIR), name="web-root")
