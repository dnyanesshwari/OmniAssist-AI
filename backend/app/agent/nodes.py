"""LangGraph nodes. Rules: identity comes from state (auth), tools validate everything, confirmation is a code gate."""
import hashlib
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent import guards
from app.agent.handoff import create_handoff
from app.agent.llm import ProviderError, classify_llm
from app.core.config import get_settings
from app.db.models import Appointment, Conversation, Service
from app.rag.answer import answer_question
from app.tools import availability, booking
from app.tools.audit import audit
from app.tools.errors import ToolError

log = logging.getLogger("agent")
IST = ZoneInfo("Asia/Kolkata")
BOOK_FIELDS = [("service_code", "which service you need"), ("city", "your city"),
               ("start_at", "the date and time you'd like"), ("address", "the service address")]
HELP = ("I can answer questions about QuickCare services, prices, warranty and cancellation, "
        "and check availability, book or cancel appointments. What would you like to do?")
APOLOGY = ("I'm having trouble reaching my AI service right now, so I haven't changed anything. "
           "Please try again in a moment.")


def _db(config) -> Session:
    return config["configurable"]["db"]


def fmt_dt(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(IST).strftime("%a %d %b, %I:%M %p IST")


def _tool(db: Session, calls: list, name: str, fn, *a, **kw):
    """Run a tool; record the call; never let an exception escape as anything but a ToolError."""
    try:
        res = fn(*a, **kw)
        calls.append({"tool": name, "ok": True})
        return res, None
    except ToolError as e:
        db.rollback()
        calls.append({"tool": name, "ok": False, "error": e.code})
        return None, e
    except Exception:
        db.rollback()
        log.exception("tool %s crashed", name)
        calls.append({"tool": name, "ok": False, "error": "internal_error"})
        return None, ToolError("internal_error", "Something went wrong on our side. Nothing was changed.")


def _fail(state, reply: str, calls: list | None = None) -> dict:
    return {"reply": reply, "failures": state.get("failures", 0) + 1, "tool_calls": calls or []}


def _ok(reply: str, calls: list, **extra) -> dict:
    return {"reply": reply, "failures": 0, "tool_calls": calls, **extra}


# ---------------------------------------------------------------- guard
def guard(state, config):
    text = state["user_text"]
    if guards.is_injection(text):
        audit(_db(config), "agent.injection_blocked", state["customer_id"], "conversation", state["conversation_id"],
              {"snippet": text[:120]})
        return {"intent": "blocked", "reply": "I can't act on that request. I can help with QuickCare services, "
                "policies and bookings — what would you like to do?"}
    reason = guards.escalation_reason(text)
    if reason:
        return {"intent": "human_handoff", "handoff": reason}
    return {}


def route_guard(state):
    if state.get("handoff"):
        return "handoff"
    return "done" if state.get("intent") == "blocked" else "pending"


# ---------------------------------------------------------------- pending confirmation gate
def pending(state, config):
    p = state.get("pending")
    if not p:
        return {}
    db, cid = _db(config), state["customer_id"]
    answer = guards.parse_yes_no(state["user_text"])
    if answer is None:
        return {"pending": None}  # user moved on; the hold simply expires, nothing is executed
    calls: list = []
    if answer == "no":
        if p["type"] == "confirm_booking":  # release the held slot right away
            _tool(db, calls, "cancel_booking", booking.cancel_booking, db, cid, p["appointment_id"], True)
            return {"pending": None, "intent": "confirmation", "reply": "No problem — I've released that slot.",
                    "tool_calls": calls}
        return {"pending": None, "intent": "confirmation", "reply": "Okay, I've kept your appointment as is."}
    # answer == "yes": only now do side-effecting tools run, always with the authenticated customer id
    if p["type"] == "confirm_booking":
        res, err = _tool(db, calls, "confirm_booking", booking.confirm_booking, db, cid, p["appointment_id"])
        if err:
            return {**_fail(state, err.message, calls), "pending": None, "intent": "confirmation"}
        a = res["appointment"]
        return {**_ok(f"Confirmed! {a['service']} on {fmt_dt(a['start_at'])} at {a['address']}. "
                      f"Technician: {a['technician']}. Amount due after service: ₹{a['price_inr']:.0f}.", calls,
                      appointment=a), "pending": None, "intent": "confirmation",
                "slots": {k: v for k, v in state.get("slots", {}).items() if k in ("city", "address")}}
    res, err = _tool(db, calls, "cancel_booking", booking.cancel_booking, db, cid, p["appointment_id"], True)
    if err:
        return {**_fail(state, err.message, calls), "pending": None, "intent": "confirmation"}
    a = res["appointment"]
    return {**_ok(f"Your {a['service']} appointment on {fmt_dt(a['start_at'])} is cancelled. "
                  f"Cancellation charge: ₹{a['cancellation_fee_inr']:.0f}.", calls, appointment=a),
            "pending": None, "intent": "confirmation"}


def route_pending(state):
    return "done" if state.get("reply") else "classify"


# ---------------------------------------------------------------- classify
def classify(state, config):
    db, s = _db(config), get_settings()
    try:
        if state.get("simulate") == "llm" and s.allow_failure_injection:
            raise ProviderError("simulated provider outage")
        codes = list(db.scalars(select(Service.code).where(Service.active)))
        out = classify_llm(state["user_text"], state.get("history", []), state.get("slots", {}),
                           datetime.now(IST).strftime("%A %Y-%m-%d %H:%M"), codes)
    except Exception as e:
        log.warning("classify failed: %s", e)
        audit(db, "agent.provider_error", state["customer_id"], "conversation", state["conversation_id"],
              {"error": type(e).__name__})
        return {**_fail(state, APOLOGY), "intent": "provider_error"}
    slots = dict(state.get("slots", {}))
    slots.update({k: v for k, v in (out.get("slots") or {}).items() if v not in (None, "")})
    return {"intent": out["intent"], "slots": slots, "query": out.get("standalone_question") or ""}


def route_intent(state):
    return {"policy_question": "policy", "check_availability": "availability", "book_appointment": "book",
            "cancel_appointment": "cancel", "list_appointments": "list", "human_handoff": "handoff",
            "provider_error": "after"}.get(state.get("intent"), "other")


# ---------------------------------------------------------------- intent nodes
def policy(state, config):
    db, calls = _db(config), []
    try:
        ans = answer_question(db, state.get("query") or state["user_text"])
    except Exception as e:
        log.warning("rag failed: %s", e)
        return {**_fail(state, APOLOGY), "intent": "provider_error"}
    calls.append({"tool": "rag_answer", "ok": not ans.abstained})
    if ans.abstained:
        n = state.get("failures", 0) + 1
        out = {"reply": ans.text, "failures": n, "tool_calls": calls, "abstained": True, "citations": []}
        if n >= get_settings().max_failures:
            out["handoff"] = "no_answer"
        return out
    return _ok(ans.text, calls, citations=ans.citations, abstained=False)


def availability_node(state, config):
    db, calls, slots = _db(config), [], state.get("slots", {})
    need = [(k, d) for k, d in (("service_code", "which service"), ("city", "your city")) if not slots.get(k)]
    day = slots.get("date") or (slots.get("start_at") or "")[:10]
    if not day:
        need.append(("date", "which date"))
    if need:
        return {"reply": "To check availability I need " + ", ".join(d for _, d in need) + ".", "tool_calls": []}
    try:
        d = datetime.fromisoformat(day).date()
    except ValueError:
        return {"reply": "I couldn't read that date. Could you give it as e.g. 18 Oct?", "tool_calls": []}
    res, err = _tool(db, calls, "check_availability", availability.check_availability, db,
                     slots["service_code"], slots["city"], d)
    if err:
        return _fail(state, err.message, calls)
    if not res["slots"]:
        return _ok(f"No free slots for {res['service']} in {res['city']} on {d:%d %b}. Want to try another day?", calls)
    shown = ", ".join(datetime.fromisoformat(x).astimezone(IST).strftime("%I:%M %p").lstrip("0") for x in res["slots"][:8])
    more = f" (+{len(res['slots']) - 8} more)" if len(res["slots"]) > 8 else ""
    return _ok(f"Available on {d:%a %d %b} in {res['city']}: {shown}{more}. Tell me a time and your address to book.", calls)


def book(state, config):
    db, cid, calls, slots = _db(config), state["customer_id"], [], state.get("slots", {})
    missing = [d for k, d in BOOK_FIELDS if not slots.get(k)]
    if missing:
        return {"reply": "To book I still need " + ", ".join(missing) + ".", "tool_calls": []}
    try:
        start = datetime.fromisoformat(slots["start_at"])
    except ValueError:
        return {"reply": "I couldn't read that date and time. Could you rephrase it?", "tool_calls": []}
    svc_id = db.scalar(select(Service.id).where(Service.code == str(slots["service_code"]).lower()))
    n = db.scalar(select(func.count()).select_from(Appointment).where(
        Appointment.customer_id == cid, Appointment.service_id == svc_id, Appointment.start_at == start)) or 0
    key = "agt-" + hashlib.sha256(f"{cid}|{svc_id}|{start.isoformat()}".encode()).hexdigest()[:24] + f"-{n}"
    res, err = _tool(db, calls, "propose_booking", booking.propose_booking, db, cid, slots["service_code"],
                     slots["city"], start, slots["address"], key)
    if err:
        return _fail(state, err.message, calls)
    a = res["appointment"]
    return {**_ok(f"I've held {a['service']} on {fmt_dt(a['start_at'])} at {a['address']} for ₹{a['price_inr']:.0f} "
                  f"(technician {a['technician']}). The hold lasts 10 minutes. Reply **yes** to confirm or **no** to drop it.",
                  calls, appointment=a),
            "pending": {"type": "confirm_booking", "appointment_id": a["id"]}}


def cancel(state, config):
    db, cid, calls = _db(config), state["customer_id"], []
    appt_id = (state.get("slots") or {}).get("appointment_id")
    if not appt_id:
        mine = [a for a in booking.list_appointments(db, cid) if a["status"] in ("held", "booked")]
        if not mine:
            return {"reply": "You don't have any active appointments.", "tool_calls": []}
        if len(mine) > 1:
            lst = "; ".join(f"#{a['id']} {a['service']} {fmt_dt(a['start_at'])}" for a in mine)
            return {"reply": f"Which one should I cancel? {lst}", "tool_calls": []}
        appt_id = mine[0]["id"]
    res, err = _tool(db, calls, "cancel_booking", booking.cancel_booking, db, cid, int(appt_id), False)
    if err:
        return _fail(state, err.message, calls)
    a = res["appointment"]
    return {**_ok(f"Cancelling {a['service']} on {fmt_dt(a['start_at'])} will cost ₹{res['cancellation_fee_inr']:.0f}. "
                  "Reply **yes** to cancel it or **no** to keep it.", calls, appointment=a),
            "pending": {"type": "cancel_booking", "appointment_id": a["id"]}}


def list_node(state, config):
    calls = []
    res, err = _tool(_db(config), calls, "list_appointments", booking.list_appointments, _db(config), state["customer_id"])
    active = [a for a in (res or []) if a["status"] in ("held", "booked")]
    if not active:
        return _ok("You have no upcoming appointments.", calls)
    return _ok("Your appointments: " + "; ".join(
        f"#{a['id']} {a['service']} {fmt_dt(a['start_at'])} ({a['status']})" for a in active), calls)


def other(state, config):
    return {"reply": HELP, "tool_calls": []}


def after(state):
    if state.get("handoff") or state.get("failures", 0) >= get_settings().max_failures:
        return "handoff"
    return "done"


# ---------------------------------------------------------------- handoff
def handoff(state, config):
    db = _db(config)
    reason = state.get("handoff") or ("customer_request" if state.get("intent") == "human_handoff" else "repeated_failures")
    conv = db.get(Conversation, state["conversation_id"])
    ticket = create_handoff(db, conv, reason)
    base = state.get("reply") or ""
    msg = (f"I'm connecting you with a human agent (ticket #{ticket.id}). I've shared a summary of our conversation "
           "so you won't need to repeat yourself.")
    prefix = base + "\n\n" if base and reason in ("repeated_failures", "no_answer") else ""
    return {"reply": prefix + msg,
            "handoff": reason, "handoff_ticket_id": ticket.id, "pending": None}
