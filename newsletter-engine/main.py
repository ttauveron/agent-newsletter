import logging
import os
from contextlib import asynccontextmanager

from anthropic import Anthropic
from fastapi import FastAPI, HTTPException

from api.routes import create_router
from config import load_settings, load_sources
from db.session import get_session
from gmail.client import GmailClient
from gmail.poller import poll
from processing.whitelist import WhitelistFilter
from scheduler import create_scheduler, load_digest_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

settings = load_settings()
sources = load_sources()
whitelist = WhitelistFilter(settings, sources)
gmail_client = GmailClient(
    token_path=os.environ.get("GMAIL_TOKEN_PATH", "/app/config/gmail_token.json")
)
anthropic_client = Anthropic()


@asynccontextmanager
async def lifespan(app: FastAPI):
    with get_session() as session:
        digest_schedule, digest_timezone = load_digest_config(session)
    scheduler = create_scheduler(
        digest_schedule, digest_timezone, gmail_client, whitelist, anthropic_client
    )
    app.state.scheduler = scheduler
    app.state.gmail_client = gmail_client
    app.state.settings = settings
    scheduler.start()
    logger.info("Scheduler started (digest at %s %s)", digest_schedule, digest_timezone)
    yield
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")


app = FastAPI(title="Newsletter Engine", lifespan=lifespan)
app.include_router(create_router(gmail_client, settings))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/trigger/poll")
def trigger_poll():
    try:
        with get_session() as session:
            stats = poll(gmail_client, whitelist, session, anthropic_client)
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("Poll failed")
        raise HTTPException(status_code=500, detail=str(e))
