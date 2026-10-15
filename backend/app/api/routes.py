from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.schemas import AskIn, CancelIn, LoginIn, MessageIn, ProposeIn, RegisterIn
from app.core.deps import current_customer
from app.core.security import create_token, hash_password, verify_password
from app.agent.handoff import create_handoff
from app.agent.runner import ConversationNotFound, run_turn
from app.db.models import Appointment, AuditEvent, Conversation, Customer, HandoffTicket, Message
from app.db.session import get_db
from app.rag.answer import answer_question
from app.tools import availability, booking, services
from app.tools.audit import audit
from app.tools.errors import ToolError

router = APIRouter()
STATUS = {"appointment_not_found": 404, "slot_unavailable": 409, "duplicate_booking": 409,
          "hold_expired": 409, "not_confirmable": 409, "not_cancellable": 409}


def _run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ToolError as e:
        raise HTTPException(STATUS.get(e.code, 422), detail=e.to_dict())


# ---- auth ----
@router.post("/auth/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    c = Customer(email=body.email.lower(), name=body.name, phone=body.phone,
                 password_hash=hash_password(body.password))
    db.add(c)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email already registered")
    audit(db, "auth.registered", c.id, "customer", c.id)
    db.commit()
    return {"token": create_token(c.id)}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    c = db.scalar(select(Customer).where(Customer.email == body.email.lower()))
    if not c or not verify_password(body.password, c.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return {"token": create_token(c.id)}


@router.get("/me")
def me(c: Customer = Depends(current_customer)):
    return {"id": c.id, "email": c.email, "name": c.name, "phone": c.phone, "is_admin": c.is_admin}


# ---- catalog / availability ----
@router.get("/services")
def get_services(db: Session = Depends(get_db)):
    return services.list_services(db)


@router.get("/availability")
def get_availability(service_code: str, city: str, day: date, db: Session = Depends(get_db),
                     _: Customer = Depends(current_customer)):
    return _run(availability.check_availability, db, service_code, city, day)


# ---- appointments ----
@router.post("/appointments/propose", status_code=201)
def propose(body: ProposeIn, db: Session = Depends(get_db), c: Customer = Depends(current_customer)):
    return _run(booking.propose_booking, db, c.id, body.service_code, body.city, body.start_at,
                body.address, body.idempotency_key)


@router.post("/appointments/{appt_id}/confirm")
def confirm(appt_id: int, db: Session = Depends(get_db), c: Customer = Depends(current_customer)):
    return _run(booking.confirm_booking, db, c.id, appt_id)


@router.post("/appointments/{appt_id}/cancel")
def cancel(appt_id: int, body: CancelIn, db: Session = Depends(get_db), c: Customer = Depends(current_customer)):
    return _run(booking.cancel_booking, db, c.id, appt_id, body.confirmed)


@router.get("/appointments")
def my_appointments(db: Session = Depends(get_db), c: Customer = Depends(current_customer)):
    return booking.list_appointments(db, c.id)


# ---- conversations / RAG ----
@router.post("/chat/ask")
def ask(body: AskIn, db: Session = Depends(get_db), c: Customer = Depends(current_customer)):
    conv = db.get(Conversation, body.conversation_id) if body.conversation_id else None
    if body.conversation_id and (not conv or conv.customer_id != c.id):
        raise HTTPException(404, "Conversation not found")
    if not conv:
        conv = Conversation(customer_id=c.id)
        db.add(conv)
        db.flush()
    db.add(Message(conversation_id=conv.id, role="user", content=body.question))
    ans = answer_question(db, body.question)
    db.add(Message(conversation_id=conv.id, role="assistant", content=ans.text, citations=ans.citations,
                   meta={"abstained": ans.abstained, "top_similarity": ans.top_similarity}))
    audit(db, "rag.answered", c.id, "conversation", conv.id,
          {"abstained": ans.abstained, "top_similarity": round(ans.top_similarity, 3)})
    db.commit()
    return {"conversation_id": conv.id, "answer": ans.text, "citations": ans.citations,
            "abstained": ans.abstained}


@router.get("/conversations")
def conversations(db: Session = Depends(get_db), c: Customer = Depends(current_customer)):
    rows = db.scalars(select(Conversation).where(Conversation.customer_id == c.id)
                      .order_by(Conversation.id.desc())).all()
    return [{"id": r.id, "channel": r.channel, "status": r.status, "created_at": r.created_at} for r in rows]


@router.get("/conversations/{conv_id}/messages")
def messages(conv_id: int, db: Session = Depends(get_db), c: Customer = Depends(current_customer)):
    conv = db.get(Conversation, conv_id)
    if not conv or conv.customer_id != c.id:
        raise HTTPException(404, "Conversation not found")
    rows = db.scalars(select(Message).where(Message.conversation_id == conv_id).order_by(Message.id)).all()
    return [{"id": m.id, "role": m.role, "content": m.content, "modality": m.modality,
             "citations": m.citations, "created_at": m.created_at} for m in rows]


# ---- agent chat (text and voice share this path) ----
@router.post("/chat/message")
def chat_message(body: MessageIn, db: Session = Depends(get_db), c: Customer = Depends(current_customer)):
    try:
        return run_turn(db, c, body.text, body.conversation_id, body.modality, body.simulate_failure)
    except ConversationNotFound:
        raise HTTPException(404, "Conversation not found")


@router.post("/conversations/{conv_id}/handoff", status_code=201)
def request_handoff(conv_id: int, db: Session = Depends(get_db), c: Customer = Depends(current_customer)):
    conv = db.get(Conversation, conv_id)
    if not conv or conv.customer_id != c.id:
        raise HTTPException(404, "Conversation not found")
    t = create_handoff(db, conv, "customer_request")
    db.commit()
    return {"ticket_id": t.id, "status": t.status}


# ---- admin ----
def admin_only(c: Customer = Depends(current_customer)) -> Customer:
    if not c.is_admin:
        raise HTTPException(403, "Admin only")
    return c


@router.get("/admin/analytics")
def analytics(db: Session = Depends(get_db), _: Customer = Depends(admin_only)):
    from collections import Counter, defaultdict
    msgs = db.scalars(select(Message).where(Message.role == "assistant", Message.meta.is_not(None))
                      .order_by(Message.id.desc()).limit(5000)).all()
    intents, tools, lat = Counter(), defaultdict(lambda: {"ok": 0, "error": 0}), []
    rag_total = rag_abstained = 0
    for m in msgs:
        meta = m.meta or {}
        intents[meta.get("intent") or "unknown"] += 1
        for t in meta.get("tool_calls", []):
            tools[t["tool"]]["ok" if t.get("ok") else "error"] += 1
            if t["tool"] == "rag_answer":
                rag_total += 1
                rag_abstained += 0 if t.get("ok") else 1
        if meta.get("latency_ms") is not None:
            lat.append(meta["latency_ms"])
    lat.sort()
    convs = db.scalar(select(func.count()).select_from(Conversation)) or 0
    tickets = db.execute(select(HandoffTicket.reason, func.count()).group_by(HandoffTicket.reason)).all()
    return {
        "conversations": convs,
        "messages": db.scalar(select(func.count()).select_from(Message)) or 0,
        "handoffs": {"total": sum(n for _, n in tickets), "by_reason": {r: n for r, n in tickets},
                     "rate": round(sum(n for _, n in tickets) / convs, 3) if convs else 0},
        "appointments_by_status": dict(db.execute(select(Appointment.status, func.count()).group_by(Appointment.status)).all()),
        "rag": {"answers": rag_total, "abstained": rag_abstained},
        "intents": dict(intents), "tools": dict(tools),
        "latency_ms": {"p50": lat[len(lat) // 2] if lat else None, "p95": lat[int(len(lat) * 0.95) - 1] if len(lat) >= 20 else (lat[-1] if lat else None)},
        "events": dict(db.execute(select(AuditEvent.event_type, func.count()).group_by(AuditEvent.event_type)).all()),
    }
