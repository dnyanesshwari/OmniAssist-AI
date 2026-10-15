"""Human handoff: ticket + deterministic summary (no LLM, so it still works during provider outages)."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import Appointment, Conversation, HandoffTicket, Message
from app.tools.audit import audit

NEXT_STEPS = {
    "sensitive_complaint": "Treat as priority. Contact the customer promptly, record the complaint, and review the technician/booking involved.",
    "customer_request": "Customer asked for a person. Call back or reply in chat and continue from the open issue below.",
    "repeated_failures": "Automated help failed repeatedly. Resolve the open issue manually and check the tool errors listed.",
    "no_answer": "Documents had no reliable answer. Answer manually and consider adding it to the knowledge base.",
}


def build_summary(db: Session, conv: Conversation, reason: str) -> str:
    msgs = db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)).all()
    user_msgs = [m.content for m in msgs if m.role == "user"]
    sources: list[str] = []
    calls: list[str] = []
    for m in msgs:
        for c in (m.citations or []):
            label = f"{c.get('document')} › {c.get('section') or 'general'}"
            if label not in sources:
                sources.append(label)
        for t in ((m.meta or {}).get("tool_calls") or []):
            calls.append(f"{t['tool']}={'ok' if t.get('ok') else 'failed:' + str(t.get('error'))}")
    open_appts = db.scalars(select(Appointment).where(
        Appointment.customer_id == conv.customer_id, Appointment.status.in_(("held", "booked")))).all()
    issue = user_msgs[-1][:300] if user_msgs else "(no customer message)"
    lines = [
        f"Reason: {reason.replace('_', ' ')}",
        f"Unresolved issue: {issue}",
        f"Earlier customer messages: {' | '.join(m[:100] for m in user_msgs[-4:-1]) or 'none'}",
        f"Document sources consulted: {'; '.join(sources) or 'none'}",
        f"Tool calls so far: {', '.join(calls[-10:]) or 'none'}",
        f"Open appointments: {', '.join(f'#{a.id} {a.service.name} {a.start_at:%d %b %H:%M} ({a.status})' for a in open_appts) or 'none'}",
        f"Recommended next steps: {NEXT_STEPS.get(reason, 'Review the conversation and follow up with the customer.')}",
    ]
    return "\n".join(lines)


def create_handoff(db: Session, conv: Conversation, reason: str) -> HandoffTicket:
    existing = db.scalar(select(HandoffTicket).where(HandoffTicket.conversation_id == conv.id,
                                                     HandoffTicket.status == "open"))
    if existing:
        return existing
    ticket = HandoffTicket(conversation_id=conv.id, customer_id=conv.customer_id, reason=reason,
                           summary=build_summary(db, conv, reason))
    db.add(ticket)
    conv.status = "handed_off"
    db.flush()
    audit(db, "handoff.created", conv.customer_id, "handoff_ticket", ticket.id, {"reason": reason})
    return ticket
