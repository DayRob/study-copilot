from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api import chat, cyber, game, graph, ingest, subjects
from app.config import get_settings
from app.db.connection import init_db
from app.ingestion.watcher import start_watcher, stop_watcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_watcher()
    yield
    stop_watcher()


app = FastAPI(title="Study Copilot", lifespan=lifespan)

settings = get_settings()
# The API has no authentication (single-user, loopback-only app), so the Host
# header is the last line of defense against DNS rebinding: a malicious page
# whose domain resolves to 127.0.0.1 becomes same-origin and could otherwise
# read every endpoint. Rejecting non-local Hosts closes that hole.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "[::1]"],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(ingest.router)
app.include_router(chat.router)
app.include_router(subjects.router)
app.include_router(graph.router)
app.include_router(game.router)
app.include_router(cyber.router)


@app.get("/health")
def health():
    return {"status": "ok"}
