import json
import logging
import os
from pathlib import Path
from string import Template
from typing import Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from db.models import Email, EmailState, Summary
from processing.state import audit, transition_state

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 4000

_PROMPT_FILE = Path(os.environ.get("ENRICHMENT_PROMPT_PATH", "/app/config/prompts/enrichment.md"))


# Load once at startup; restart required after editing the file.
def _load_prompt_template() -> str:
    if _PROMPT_FILE.exists():
        return _PROMPT_FILE.read_text()
    logger.warning("Enrichment prompt file not found at %s, using built-in fallback", _PROMPT_FILE)
    return """\
You are processing a newsletter email for a tech security professional.

Subject: $subject
Sender: $sender_email
Category: $category

Content:
$content

Return JSON only, no other text:
{
  "summary": "2-3 sentence factual summary of the main content",
  "key_points": ["3 to 5 key points as short sentences"],
  "tags": ["3 to 7 relevant topic tags"]
}"""


_PROMPT = _load_prompt_template()


def _truncate(content: str, max_chars: int = MAX_CONTENT_CHARS) -> str:
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n[truncated]"


def _build_prompt(email: Email) -> str:
    return Template(_PROMPT).safe_substitute(
        subject=email.subject or "",
        sender_email=email.sender_email,
        category=email.source_category or "",
        content=_truncate(email.cleaned_content or ""),
    )


def _parse_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    data = json.loads(text)
    return {
        "summary": str(data.get("summary", "")),
        "key_points": list(data.get("key_points", [])),
        "tags": list(data.get("tags", [])),
    }


def enrich_email(email: Email, session: Session, client: OpenAI) -> Optional[Summary]:
    if os.environ.get("ENRICHMENT_BACKEND", "").lower() == "local":
        data = _local_enrichment(email)
        return _store_summary(
            email=email,
            session=session,
            data=data,
            model_used="local-e2e",
            tokens_input=0,
            tokens_output=0,
        )

    try:
        response = client.chat.completions.create(
            model="enrichment",
            max_tokens=512,
            messages=[{"role": "user", "content": _build_prompt(email)}],
        )
        data = _parse_response(response.choices[0].message.content)
    except Exception:
        logger.exception("Enrichment failed for email %s — staying in cleaned state", email.id)
        return None

    return _store_summary(
        email=email,
        session=session,
        data=data,
        model_used=response.model,
        tokens_input=response.usage.prompt_tokens,
        tokens_output=response.usage.completion_tokens,
    )


def _local_enrichment(email: Email) -> dict:
    content = (email.cleaned_content or "").strip()
    summary = _truncate(content, max_chars=240) if content else email.subject or "Local summary."
    return {
        "summary": summary,
        "key_points": [summary],
        "tags": [email.source_category or "local"],
    }


def _store_summary(
    email: Email,
    session: Session,
    data: dict,
    model_used: str,
    tokens_input: int,
    tokens_output: int,
) -> Summary:
    summary = Summary(
        email_id=email.id,
        summary_text=data["summary"],
        key_points=data["key_points"],
        tags=data["tags"],
        model_used=model_used,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
    )
    session.add(summary)

    email.processing_state = EmailState.ready_for_hermes
    transition_state(
        session, "email", email.id, EmailState.summarized, from_state=EmailState.cleaned
    )
    transition_state(
        session,
        "email",
        email.id,
        EmailState.ready_for_hermes,
        from_state=EmailState.summarized,
    )
    audit(
        session,
        event_type="email_enriched",
        entity_type="email",
        entity_id=email.id,
        payload={
            "model": model_used,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "tags": data["tags"],
        },
    )

    logger.info(
        "Enriched email %s: %d tags, %d tokens total",
        email.id,
        len(data["tags"]),
        tokens_input + tokens_output,
    )
    return summary
