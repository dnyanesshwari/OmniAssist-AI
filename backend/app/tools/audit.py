from sqlalchemy.orm import Session
from app.db.models import AuditEvent


def audit(db: Session, event_type: str, customer_id: int | None = None, entity: str | None = None,
          entity_id: int | None = None, payload: dict | None = None, request_id: str | None = None) -> None:
    db.add(AuditEvent(customer_id=customer_id, event_type=event_type, entity=entity,
                      entity_id=entity_id, payload=payload, request_id=request_id))
