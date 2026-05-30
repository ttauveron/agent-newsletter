import json
import uuid
from unittest.mock import MagicMock

import pytest

from processing.enrichment import (
    MAX_CONTENT_CHARS,
    _build_prompt,
    _parse_response,
    _truncate,
    enrich_email,
)

# --- _truncate ---


def test_truncate_short_content_unchanged():
    assert _truncate("hello") == "hello"


def test_truncate_exact_limit_unchanged():
    content = "x" * MAX_CONTENT_CHARS
    assert _truncate(content) == content


def test_truncate_over_limit():
    content = "x" * (MAX_CONTENT_CHARS + 100)
    result = _truncate(content)
    assert len(result) < len(content)
    assert result.endswith("[truncated]")


def test_truncate_custom_limit():
    assert _truncate("hello world", max_chars=5) == "hello\n[truncated]"


def test_truncate_empty():
    assert _truncate("") == ""


# --- _parse_response ---


def test_parse_response_valid():
    text = json.dumps(
        {
            "summary": "A brief summary.",
            "key_points": ["Point 1", "Point 2"],
            "tags": ["security", "cloud"],
        }
    )
    result = _parse_response(text)
    assert result["summary"] == "A brief summary."
    assert result["key_points"] == ["Point 1", "Point 2"]
    assert result["tags"] == ["security", "cloud"]


def test_parse_response_missing_optional_fields():
    text = json.dumps({"summary": "Only a summary."})
    result = _parse_response(text)
    assert result["summary"] == "Only a summary."
    assert result["key_points"] == []
    assert result["tags"] == []


def test_parse_response_invalid_json_raises():
    with pytest.raises(json.JSONDecodeError):
        _parse_response("not json at all")


def test_parse_response_strips_markdown_fences():
    payload = {"summary": "S", "key_points": ["p1"], "tags": ["t1"]}
    text = f"```json\n{json.dumps(payload)}\n```"
    result = _parse_response(text)
    assert result["summary"] == "S"
    assert result["tags"] == ["t1"]


def test_parse_response_strips_plain_fences():
    payload = {"summary": "S", "key_points": [], "tags": []}
    text = f"```\n{json.dumps(payload)}\n```"
    result = _parse_response(text)
    assert result["summary"] == "S"


def test_parse_response_summary_coerced_to_string():
    text = json.dumps({"summary": 42})
    result = _parse_response(text)
    assert result["summary"] == "42"


# --- _build_prompt ---


def _make_email(**kwargs):
    email = MagicMock()
    email.subject = kwargs.get("subject", "Test Subject")
    email.sender_email = kwargs.get("sender_email", "sender@example.com")
    email.source_category = kwargs.get("source_category", "cloud_security")
    email.cleaned_content = kwargs.get("cleaned_content", "Some content.")
    return email


def test_build_prompt_includes_subject():
    email = _make_email(subject="Weekly Security Digest")
    prompt = _build_prompt(email)
    assert "Weekly Security Digest" in prompt


def test_build_prompt_includes_sender():
    email = _make_email(sender_email="news@example.com")
    prompt = _build_prompt(email)
    assert "news@example.com" in prompt


def test_build_prompt_includes_category():
    email = _make_email(source_category="market_signal")
    prompt = _build_prompt(email)
    assert "market_signal" in prompt


def test_build_prompt_truncates_long_content():
    email = _make_email(cleaned_content="x" * (MAX_CONTENT_CHARS + 500))
    prompt = _build_prompt(email)
    assert "[truncated]" in prompt


def test_build_prompt_handles_none_subject():
    email = _make_email(subject=None)
    prompt = _build_prompt(email)
    assert prompt is not None


def test_build_prompt_handles_none_category():
    email = _make_email(source_category=None)
    prompt = _build_prompt(email)
    assert prompt is not None


# --- enrich_email ---


def _make_openai_mock(summary="Summary.", key_points=None, tags=None):
    response_text = json.dumps(
        {
            "summary": summary,
            "key_points": key_points or ["Point A", "Point B"],
            "tags": tags or ["iam", "cloud"],
        }
    )
    mock = MagicMock()
    mock.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=response_text))],
        model="claude-haiku-4-5-20251001",
        usage=MagicMock(prompt_tokens=120, completion_tokens=60),
    )
    return mock


def test_enrich_email_returns_summary():
    email = _make_email()
    email.id = uuid.uuid4()
    session = MagicMock()
    client = _make_openai_mock(summary="This is the summary.")

    result = enrich_email(email, session, client)

    assert result is not None
    assert result.summary_text == "This is the summary."
    assert result.model_used == "claude-haiku-4-5-20251001"
    assert result.tokens_input == 120
    assert result.tokens_output == 60


def test_enrich_email_adds_summary_to_session():
    email = _make_email()
    email.id = uuid.uuid4()
    session = MagicMock()
    client = _make_openai_mock()

    enrich_email(email, session, client)

    assert session.add.called


def test_enrich_email_sets_state_to_ready_for_hermes():
    from db.models import EmailState

    email = _make_email()
    email.id = uuid.uuid4()
    session = MagicMock()
    client = _make_openai_mock()

    enrich_email(email, session, client)

    assert email.processing_state == EmailState.ready_for_hermes


def test_enrich_email_returns_none_on_api_failure():
    email = _make_email()
    email.id = uuid.uuid4()
    session = MagicMock()
    client = MagicMock()
    client.chat.completions.create.side_effect = Exception("API error")

    result = enrich_email(email, session, client)

    assert result is None


def test_enrich_email_returns_none_on_invalid_json():
    email = _make_email()
    email.id = uuid.uuid4()
    session = MagicMock()
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="not json"))]
    )

    result = enrich_email(email, session, client)

    assert result is None


def test_enrich_email_local_backend(monkeypatch):
    from db.models import EmailState

    monkeypatch.setenv("ENRICHMENT_BACKEND", "local")
    email = _make_email(cleaned_content="Local content.", source_category="cloud_security")
    email.id = uuid.uuid4()
    session = MagicMock()
    client = MagicMock()

    result = enrich_email(email, session, client)

    assert result is not None
    assert result.summary_text == "Local content."
    assert result.model_used == "local-e2e"
    assert result.tags == ["cloud_security"]
    assert email.processing_state == EmailState.ready_for_hermes
    client.chat.completions.create.assert_not_called()
