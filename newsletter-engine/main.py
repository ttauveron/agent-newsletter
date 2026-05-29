import logging
import os

from anthropic import Anthropic
from fastapi import FastAPI, HTTPException

from config import load_settings, load_sources
from db.session import get_session
from gmail.client import GmailClient
from gmail.poller import poll
from processing.whitelist import WhitelistFilter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

settings = load_settings()
sources = load_sources()
whitelist = WhitelistFilter(settings, sources)
gmail_client = GmailClient(
    token_path=os.environ.get("GMAIL_TOKEN_PATH", "/app/config/gmail_token.json")
)
anthropic_client = Anthropic()

app = FastAPI(title="Newsletter Engine")


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
