"""One conversational turn: load state -> run graph -> persist. Same path for text and voice."""
import threading
import time
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.agent.graph import GRAPH
from app.db.models import Conversation, Customer, Message
from app.tools.audit import audit


class TurnCancelled(Exception):
    """User barged in; the result of this turn is discarded (no assistant message, no state change)."""


class ConversationNotFound(Exception):
    pass


def load_or_create(db: Session, customer: Customer, conversation_id: int | None, modality: str) -> Conversation:
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if not conv or conv.customer_id != customer.id:
            raise ConversationNotFound()
    else:
        conv = Conversation(customer_id=customer.id, channel=modality, state={})
        db.add(conv)
        db.flush()
    if conv.channel != modality and conv.channel != "mixed":
        conv.channel = "mixed"
    return conv


def run_turn(db: Session, customer: Customer, text: str, conversation_id: int | None = None,
             modality: str = "text", simulate: str | None = None,
             cancel_event: threading.Event | None = None) -> dict:
    t0 = time.perf_counter()
    conv = load_or_create(db, customer, conversation_id, modality)
    db.add(Message(conversation_id=conv.id, role="user", content=text, modality=modality))
    db.commit()  # the user's words are persisted even if the rest of the turn fails or is cancelled

    if conv.status == "handed_off":
        reply = "A human agent has been notified and will reply here soon. Your message has been added to the ticket."
        db.add(Message(conversation_id=conv.id, role="assistant", content=reply, modality=modality,
                       meta={"intent": "handed_off"}))
        db.commit()
        return {"conversation_id": conv.id, "reply": reply, "citations": [], "intent": "handed_off",
                "pending": None, "appointment": None, "handoff": True, "ticket_id": None, "status": conv.status}

    st = conv.state or {}
    history = [{"role": m.role, "content": m.content} for m in reversed(db.scalars(
        select(Message).where(Message.conversation_id == conv.id, Message.role.in_(("user", "assistant")))
        .order_by(Message.id.desc()).offset(1).limit(8)).all())]
    out = GRAPH.invoke(
        {"customer_id": customer.id, "conversation_id": conv.id, "user_text": text, "modality": modality,
         "history": history, "simulate": simulate, "slots": st.get("slots", {}), "pending": st.get("pending"),
         "failures": st.get("failures", 0), "tool_calls": [], "citations": [], "appointment": None},
        config={"configurable": {"db": db}})

    if cancel_event is not None and cancel_event.is_set():
        db.rollback()
        raise TurnCancelled()

    reply = out.get("reply") or "Sorry, I couldn't process that. Could you rephrase?"
    meta = {"intent": out.get("intent"), "tool_calls": out.get("tool_calls", []), "abstained": out.get("abstained", False),
            "handoff": out.get("handoff"), "latency_ms": int((time.perf_counter() - t0) * 1000)}
    db.add(Message(conversation_id=conv.id, role="assistant", content=reply, modality=modality,
                   citations=out.get("citations") or None, meta=meta))
    conv.state = {"slots": out.get("slots", {}), "pending": out.get("pending"), "failures": out.get("failures", 0)}
    audit(db, "agent.turn", customer.id, "conversation", conv.id,
          {"intent": out.get("intent"), "modality": modality, "latency_ms": meta["latency_ms"]})
    db.commit()
    return {"conversation_id": conv.id, "reply": reply, "citations": out.get("citations") or [],
            "intent": out.get("intent"), "pending": out.get("pending"), "appointment": out.get("appointment"),
            "handoff": bool(out.get("handoff")), "ticket_id": out.get("handoff_ticket_id"), "status": conv.status}
