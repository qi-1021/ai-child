"""
AI Child Server – FastAPI entry point.

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.chat import router as chat_router
from api.teach import router as teach_router
from config import settings
from models import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initialising database …")
    await init_db()
    logger.info("AI Child server is ready.")
    yield
    logger.info("AI Child server shutting down.")


app = FastAPI(
    title="AI Child",
    description=(
        "An autonomous learning AI that grows through conversation, "
        "remembers what it is taught, and proactively asks questions."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve saved media files
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

app.include_router(chat_router)
app.include_router(teach_router)


@app.get("/", tags=["health"])
async def root():
    return {
        "name": "AI Child",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
