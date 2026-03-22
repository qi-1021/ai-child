"""
AI Child Server – FastAPI entry point.

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from ai.profile import ensure_name_question_exists, get_ai_name
from ai.sleep import initialize_sleep_state, sleep_scheduler
from ai.llm_provider import initialize_llm_provider
from ai.social_learner import rss_poll_scheduler
from api.chat import router as chat_router
from api.sleep import router as sleep_router
from api.social import router as social_router
from api.teach import router as teach_router
from config import settings
from models import async_session, get_session, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

UI_DIR = Path(__file__).parent / "ui"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initialising LLM provider …")
    initialize_llm_provider()
    logger.info("Initialising database …")
    await init_db()
    # Ensure the name-seeking question exists on every fresh start
    async with async_session() as session:
        await ensure_name_question_exists(session)
    # Set sleep state based on current time, then start the scheduler
    await initialize_sleep_state()
    asyncio.create_task(sleep_scheduler())
    asyncio.create_task(rss_poll_scheduler())
    logger.info("AI Child server is ready.")
    yield
    logger.info("AI Child server shutting down.")


app = FastAPI(
    title="AI Child",
    description=(
        "An autonomous learning AI that grows through conversation, "
        "asks questions, searches the web, and creates its own tools."
    ),
    version="0.3.0",
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
app.include_router(sleep_router)
app.include_router(social_router)


@app.get("/", tags=["ui"])
async def root():
    """Serve the graphical UI. Returns the single-page app HTML."""
    ui_file = UI_DIR / "index.html"
    if ui_file.exists():
        return FileResponse(str(ui_file), media_type="text/html")
    # Fallback JSON response if UI file is missing (e.g., during tests)
    return {
        "name": "AI Child",
        "status": "running",
        "docs": "/docs",
        "version": "0.3.0",
    }


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


@app.get("/profile", tags=["profile"])
async def get_profile(session: AsyncSession = Depends(get_session)):
    """Return the AI child's current profile (name, whether it has been named)."""
    name = await get_ai_name(session)
    return {"name": name, "has_name": name is not None}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )

