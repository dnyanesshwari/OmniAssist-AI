"""Booking tools. All rules live here — never delegated to the LLM.
Flow: propose_booking (holds slot) -> confirm_booking (customer's explicit yes) ; cancel_booking(confirmed=False) previews the fee."""
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.models import Appointment
from app.tools.audit import audit
from app.tools.availability import expire_stale_holds, free_technicians, now_utc, validate_start
from app.tools.errors import ToolError
from app.tools.services import get_service, normalize_city


def appt_dict(a: Appointment) -> dict:
    return {"id": a.id, "status": a.status, "service": a.service.name, "service_code": a.service.code,
            "city": a.city, "address": a.address, "start_at": a.start_at.isoformat(),
            "end_at": a.end_at.isoformat(), "technician": a.technician.name,
            "price_inr": float(a.price_inr),
            "cancellation_fee_inr": float(a.cancellation_fee_inr) if a.cancellation_fee_inr is not None else None,
            "hold_expires_at": a.hold_expires_at.isoformat() if a.hold_expires_at else None}


def cancellation_fee(price: Decimal, start_at: datetime, now: datetime | None = None) -> Decimal:
    """>24h: free | 2–24h: 20% | <2h: 50%  (mirrors data/documents/cancellation_policy.md)"""
    hours = (start_at - (now or now_utc())).total_seconds() / 3600
    pct = Decimal("0") if hours > 24 else Decimal("0.20") if hours >= 2 else Decimal("0.50")
    return (price * pct).quantize(Decimal("0.01"))


def propose_booking(db: Session, customer_id: int, service_code: str, city: str, start_at: datetime,
                    address: str, idempotency_key: str, request_id: str | None = None) -> dict:
    s = get_settings()
    if not (5 <= len(address.strip()) <= 300):
        raise ToolError("invalid_address", "Please provide a valid service address.")
    if not (8 <= len(idempotency_key) <= 80):
        raise ToolError("invalid_idempotency_key", "idempotency_key must be 8–80 characters.")

    prior = db.scalar(select(Appointment).where(Appointment.customer_id == customer_id,
                                                Appointment.idempotency_key == idempotency_key))
    if prior:  # replay of the same request -> same result, no new row
        return {"ok": True, "replayed": True, "appointment": appt_dict(prior)}

    svc, city = get_service(db, service_code), normalize_city(city)
    start = validate_start(start_at, svc.duration_min)
    end = start + timedelta(minutes=svc.duration_min)
    expire_stale_holds(db)

    dup = db.scalar(select(Appointment).where(
        Appointment.customer_id == customer_id, Appointment.service_id == svc.id,
        Appointment.start_at == start, Appointment.status.in_(("held", "booked"))))
    if dup:
        raise ToolError("duplicate_booking", f"You already have this service at that time (id {dup.id}).")

    for tech in free_technicians(db, svc, city, start, end):
        appt = Appointment(customer_id=customer_id, service_id=svc.id, technician_id=tech.id, city=city,
                           address=address.strip(), start_at=start, end_at=end, status="held",
                           hold_expires_at=now_utc() + timedelta(minutes=s.hold_minutes),
                           price_inr=svc.base_price_inr, idempotency_key=idempotency_key)
        try:
            with db.begin_nested():  # savepoint: DB exclusion constraint is the final race guard
                db.add(appt)
                db.flush()
        except IntegrityError:
            continue
        audit(db, "booking.proposed", customer_id, "appointment", appt.id, {"start": start.isoformat()}, request_id)
        db.commit()
        db.refresh(appt)
        return {"ok": True, "requires_confirmation": True, "appointment": appt_dict(appt),
                "message": f"Slot held for {s.hold_minutes} minutes. Ask the customer to confirm."}
    raise ToolError("slot_unavailable", "That time is no longer available. Please pick another slot.")


def _own_appointment(db: Session, customer_id: int, appointment_id: int) -> Appointment:
    appt = db.scalar(select(Appointment).where(Appointment.id == appointment_id,
                                               Appointment.customer_id == customer_id).with_for_update())
    if not appt:  # same error for "missing" and "someone else's" -> no data leak
        raise ToolError("appointment_not_found", "Appointment not found.")
    return appt


def confirm_booking(db: Session, customer_id: int, appointment_id: int, request_id: str | None = None) -> dict:
    appt = _own_appointment(db, customer_id, appointment_id)
    if appt.status == "booked":
        return {"ok": True, "replayed": True, "appointment": appt_dict(appt)}
    if appt.status != "held":
        raise ToolError("not_confirmable", f"Appointment is {appt.status}; please start a new booking.")
    if appt.hold_expires_at and appt.hold_expires_at < now_utc():
        appt.status = "expired"
        db.commit()
        raise ToolError("hold_expired", "The hold expired. Please start a new booking.")
    appt.status, appt.hold_expires_at = "booked", None
    audit(db, "booking.confirmed", customer_id, "appointment", appt.id, None, request_id)
    db.commit()
    return {"ok": True, "appointment": appt_dict(appt)}


def list_appointments(db: Session, customer_id: int) -> list[dict]:
    rows = db.scalars(select(Appointment).where(Appointment.customer_id == customer_id,
                                                Appointment.status.in_(("held", "booked", "cancelled")))
                      .order_by(Appointment.start_at.desc())).all()
    return [appt_dict(a) for a in rows]


def cancel_booking(db: Session, customer_id: int, appointment_id: int, confirmed: bool = False,
                   request_id: str | None = None) -> dict:
    appt = _own_appointment(db, customer_id, appointment_id)
    if appt.status == "cancelled":
        return {"ok": True, "replayed": True, "appointment": appt_dict(appt)}
    if appt.status not in ("held", "booked"):
        raise ToolError("not_cancellable", f"Appointment is {appt.status}.")
    fee = Decimal("0.00") if appt.status == "held" else cancellation_fee(appt.price_inr, appt.start_at)
    if not confirmed:
        return {"ok": True, "requires_confirmation": True, "cancellation_fee_inr": float(fee),
                "appointment": appt_dict(appt),
                "message": f"Cancelling will cost ₹{fee}. Ask the customer to confirm."}
    appt.status, appt.cancelled_at, appt.cancellation_fee_inr = "cancelled", now_utc(), fee
    audit(db, "booking.cancelled", customer_id, "appointment", appt.id, {"fee": float(fee)}, request_id)
    db.commit()
    return {"ok": True, "appointment": appt_dict(appt)}
