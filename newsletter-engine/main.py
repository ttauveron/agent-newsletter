import logging
from contextlib import asynccontextmanager

from anthropic import Anthropic
from fastapi import FastAPI, HTTPException

from api.dev_routes import create_dev_router
from api.routes import create_router
from config import load_settings, load_sources
from db.session import get_session
from gmail.factory import create_email_client
from gmail.local_client import LocalEmailClient
from gmail.poller import poll
from processing.whitelist import WhitelistFilter
from scheduler import _check_user_messages, _run_daily_digest, create_scheduler, load_digest_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

settings = load_settings()
sources = load_sources()
whitelist = WhitelistFilter(settings, sources)
gmail_client = create_email_client()
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
if isinstance(gmail_client, LocalEmailClient):
    app.include_router(create_dev_router(gmail_client))


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


@app.post("/trigger/digest")
async def trigger_digest():
    try:
        await _run_daily_digest()
        return {"status": "ok"}
    except Exception as e:
        logger.exception("Digest trigger failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trigger/check-messages")
async def trigger_check_messages():
    try:
        await _check_user_messages()
        return {"status": "ok"}
    except Exception as e:
        logger.exception("Check messages trigger failed")
        raise HTTPException(status_code=500, detail=str(e))
