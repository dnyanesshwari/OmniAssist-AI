import threading
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.db.models import AuditEvent, Customer, Technician, TechnicianService, Service
from app.db.session import SessionLocal
from app.tools import booking
from app.tools.availability import check_availability, now_utc
from app.tools.errors import ToolError

IST = ZoneInfo("Asia/Kolkata")


def tomorrow_at(hour: int, minute: int = 0, days: int = 2) -> datetime:
    d = (datetime.now(IST) + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return d


def mk_customer(db, n=1) -> Customer:
    c = Customer(email=f"c{n}@example.com", name=f"C{n}", password_hash="x")
    db.add(c)
    db.commit()
    return c


def propose(db, cust, key="key-00000001", start=None, svc="ac_service", city="Pune"):
    return booking.propose_booking(db, cust.id, svc, city, start or tomorrow_at(10), "12 MG Road, Pune", key)


def test_propose_then_confirm(seeded):
    c = mk_customer(seeded)
    r = propose(seeded, c)
    assert r["requires_confirmation"] and r["appointment"]["status"] == "held"
    r2 = booking.confirm_booking(seeded, c.id, r["appointment"]["id"])
    assert r2["appointment"]["status"] == "booked"
    assert seeded.scalar(select(AuditEvent).where(AuditEvent.event_type == "booking.confirmed"))


def test_idempotent_replay_creates_one_row(seeded):
    c = mk_customer(seeded)
    a = propose(seeded, c)
    b = propose(seeded, c)
    assert b["replayed"] and a["appointment"]["id"] == b["appointment"]["id"]
    assert len(booking.list_appointments(seeded, c.id)) == 1


def test_duplicate_same_slot_different_key_blocked(seeded):
    c = mk_customer(seeded)
    propose(seeded, c, key="key-00000001")
    with pytest.raises(ToolError) as e:
        propose(seeded, c, key="key-00000002")
    assert e.value.code == "duplicate_booking"


def test_confirm_is_idempotent(seeded):
    c = mk_customer(seeded)
    aid = propose(seeded, c)["appointment"]["id"]
    booking.confirm_booking(seeded, c.id, aid)
    assert booking.confirm_booking(seeded, c.id, aid)["replayed"]


@pytest.mark.parametrize("start,code", [
    (lambda: (datetime.now(IST) + timedelta(minutes=30)).replace(minute=(datetime.now(IST).minute // 30) * 30, second=0, microsecond=0), "too_soon"),
    (lambda: tomorrow_at(7), "outside_hours"),
    (lambda: tomorrow_at(19, 30), "outside_hours"),  # 60-min service would end 20:30
    (lambda: tomorrow_at(10, 15), "invalid_time"),
])
def test_rule_violations(seeded, start, code):
    c = mk_customer(seeded)
    with pytest.raises(ToolError) as e:
        propose(seeded, c, start=start())
    assert e.value.code == code


def test_unsupported_city_and_service(seeded):
    c = mk_customer(seeded)
    with pytest.raises(ToolError) as e:
        propose(seeded, c, city="Jaipur")
    assert e.value.code == "city_not_supported"
    with pytest.raises(ToolError) as e:
        propose(seeded, c, svc="rocket_repair")
    assert e.value.code == "service_not_found"


def test_expired_hold_frees_slot_and_cannot_be_confirmed(seeded):
    c = mk_customer(seeded)
    aid = propose(seeded, c)["appointment"]["id"]
    from app.db.models import Appointment
    a = seeded.get(Appointment, aid)
    a.hold_expires_at = now_utc() - timedelta(minutes=1)
    seeded.commit()
    with pytest.raises(ToolError) as e:
        booking.confirm_booking(seeded, c.id, aid)
    assert e.value.code == "hold_expired"


@pytest.mark.parametrize("hours,pct", [(48, 0), (10, Decimal("0.20")), (1, Decimal("0.50"))])
def test_cancellation_fee_tiers(hours, pct):
    now = now_utc()
    fee = booking.cancellation_fee(Decimal("599"), now + timedelta(hours=hours), now)
    assert fee == (Decimal("599") * Decimal(pct)).quantize(Decimal("0.01"))


def test_cancel_requires_confirmation_then_is_idempotent(seeded):
    c = mk_customer(seeded)
    aid = propose(seeded, c)["appointment"]["id"]
    booking.confirm_booking(seeded, c.id, aid)
    preview = booking.cancel_booking(seeded, c.id, aid, confirmed=False)
    assert preview["requires_confirmation"] and preview["appointment"]["status"] == "booked"
    done = booking.cancel_booking(seeded, c.id, aid, confirmed=True)
    assert done["appointment"]["status"] == "cancelled" and done["appointment"]["cancellation_fee_inr"] == 0
    assert booking.cancel_booking(seeded, c.id, aid, confirmed=True)["replayed"]


def test_customer_cannot_touch_anothers_appointment(seeded):
    a, b = mk_customer(seeded, 1), mk_customer(seeded, 2)
    aid = propose(seeded, a)["appointment"]["id"]
    for fn in (lambda: booking.confirm_booking(seeded, b.id, aid),
               lambda: booking.cancel_booking(seeded, b.id, aid, True)):
        with pytest.raises(ToolError) as e:
            fn()
        assert e.value.code == "appointment_not_found"
    assert booking.list_appointments(seeded, b.id) == []


def test_availability_hides_taken_slots(seeded):
    c = mk_customer(seeded)
    start = tomorrow_at(10)
    day = start.date()
    before = check_availability(seeded, "ac_service", "Pune", day)["slots"]
    assert start.isoformat() in before
    # 2 techs in Pune do ac_service: take both
    propose(seeded, c, key="key-00000001", start=start)
    c2 = mk_customer(seeded, 2)
    propose(seeded, c2, key="key-00000002", start=start)
    after = check_availability(seeded, "ac_service", "Pune", day)["slots"]
    assert start.isoformat() not in after
    c3 = mk_customer(seeded, 3)
    with pytest.raises(ToolError) as e:
        propose(seeded, c3, key="key-00000003", start=start)
    assert e.value.code == "slot_unavailable"


def test_concurrent_requests_cannot_double_book_last_technician(db):
    """Only one technician exists; 6 customers race for the same slot -> exactly one wins."""
    svc = Service(code="solo", name="Solo", base_price_inr=Decimal(100), duration_min=60)
    tech = Technician(name="Solo Tech", city="Pune")
    db.add_all([svc, tech])
    db.flush()
    db.add(TechnicianService(technician_id=tech.id, service_id=svc.id))
    customers = [mk_customer(db, i) for i in range(6)]
    start = tomorrow_at(11)
    results, lock = [], threading.Lock()

    def worker(cust_id, n):
        with SessionLocal() as s:
            try:
                booking.propose_booking(s, cust_id, "solo", "Pune", start, "Some Address 1", f"race-key-{n:04d}")
                out = "ok"
            except ToolError as e:
                out = e.code
            with lock:
                results.append(out)

    threads = [threading.Thread(target=worker, args=(c.id, i)) for i, c in enumerate(customers)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count("ok") == 1
    assert results.count("slot_unavailable") == 5
