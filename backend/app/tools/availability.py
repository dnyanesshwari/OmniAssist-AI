from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.models import Appointment, Service, Technician, TechnicianService
from app.tools.services import get_service, normalize_city

IST = ZoneInfo("Asia/Kolkata")


def now_utc() -> datetime:
    return datetime.now(tz=ZoneInfo("UTC"))


def expire_stale_holds(db: Session) -> None:
    db.execute(update(Appointment)
               .where(Appointment.status == "held", Appointment.hold_expires_at < now_utc())
               .values(status="expired"))


def free_technicians(db: Session, service: Service, city: str, start: datetime, end: datetime) -> list[Technician]:
    busy = select(Appointment.technician_id).where(
        Appointment.status.in_(("held", "booked")),
        Appointment.start_at < end, Appointment.end_at > start,
    )
    return list(db.scalars(
        select(Technician)
        .join(TechnicianService, TechnicianService.technician_id == Technician.id)
        .where(Technician.active, Technician.city == city,
               TechnicianService.service_id == service.id, Technician.id.not_in(busy))
        .order_by(Technician.id)
    ))


def validate_start(start: datetime, duration_min: int) -> datetime:
    s = get_settings()
    if start.tzinfo is None:
        start = start.replace(tzinfo=IST)  # naive input is interpreted as IST
    local = start.astimezone(IST)
    from app.tools.errors import ToolError
    if local.second or local.microsecond or local.minute not in (0, 30):
        raise ToolError("invalid_time", "Appointments start on the hour or half hour.")
    if start < now_utc() + timedelta(hours=s.min_lead_hours):
        raise ToolError("too_soon", f"Bookings need at least {s.min_lead_hours} hours' notice.")
    end_local = local + timedelta(minutes=duration_min)
    day_end = local.replace(hour=s.work_end_hour, minute=0)
    if local.hour < s.work_start_hour or end_local > day_end:
        raise ToolError("outside_hours",
                        f"Service hours are {s.work_start_hour}:00–{s.work_end_hour}:00 IST.")
    return start


def check_availability(db: Session, service_code: str, city: str, day: date) -> dict:
    s = get_settings()
    svc, city = get_service(db, service_code), normalize_city(city)
    expire_stale_holds(db)
    slots, step = [], timedelta(minutes=30)
    cur = datetime(day.year, day.month, day.day, s.work_start_hour, tzinfo=IST)
    day_end = datetime(day.year, day.month, day.day, s.work_end_hour, tzinfo=IST)
    earliest = now_utc() + timedelta(hours=s.min_lead_hours)
    while cur + timedelta(minutes=svc.duration_min) <= day_end:
        end = cur + timedelta(minutes=svc.duration_min)
        if cur >= earliest and free_technicians(db, svc, city, cur, end):
            slots.append(cur.isoformat())
        cur += step
    return {"ok": True, "service": svc.code, "city": city, "date": day.isoformat(), "slots": slots}
