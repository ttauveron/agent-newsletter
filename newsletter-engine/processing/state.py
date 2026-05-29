import uuid
from typing import Optional

from sqlalchemy.orm import Session

from db.models import AuditLog, ProcessingEvent


def transition_state(
    session: Session,
    entity_type: str,
    entity_id: uuid.UUID,
    to_state: str,
    from_state: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    session.add(ProcessingEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        from_state=from_state,
        to_state=to_state,
        event_metadata=metadata,
    ))


def audit(
    session: Session,
    event_type: str,
    payload: dict,
    entity_type: Optional[str] = None,
    entity_id: Optional[uuid.UUID] = None,
) -> None:
    session.add(AuditLog(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    ))
