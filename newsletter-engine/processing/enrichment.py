import json
import logging
import os
from typing import Optional

from anthropic import Anthropic
from sqlalchemy.orm import Session

from db.models import Email, EmailState, Summary
from processing.state import audit, transition_state

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 4000

_PROMPT = """\
You are processing a newsletter email for a tech security professional.

Subject: {subject}
Sender: {sender_email}
Category: {category}

Content:
{content}

Return JSON only, no other text:
{{
  "summary": "2-3 sentence factual summary of the main content",
  "key_points": ["3 to 5 key points as short sentences"],
  "tags": ["3 to 7 relevant topic tags"]
}}"""


def _truncate(content: str, max_chars: int = MAX_CONTENT_CHARS) -> str:
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n[truncated]"


def _build_prompt(email: Email) -> str:
    return _PROMPT.format(
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


def enrich_email(email: Email, session: Session, client: Anthropic) -> Optional[Summary]:
    """Call Haiku to summarize and tag a cleaned email. Returns None on failure (non-fatal)."""
    if os.environ.get("ENRICHMENT_BACKEND", "anthropic").lower() == "local":
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
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": _build_prompt(email)}],
        )
        data = _parse_response(response.content[0].text)
    except Exception:
        logger.exception("Enrichment failed for email %s — staying in cleaned state", email.id)
        return None

    return _store_summary(
        email=email,
        session=session,
        data=data,
        model_used=response.model,
        tokens_input=response.usage.input_tokens,
        tokens_output=response.usage.output_tokens,
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
