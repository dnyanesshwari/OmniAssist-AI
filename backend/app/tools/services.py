from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.models import Service
from app.tools.errors import ToolError


def list_services(db: Session) -> list[dict]:
    rows = db.scalars(select(Service).where(Service.active).order_by(Service.name)).all()
    return [service_dict(s) for s in rows]


def get_service(db: Session, code: str) -> Service:
    svc = db.scalar(select(Service).where(Service.code == code.strip().lower(), Service.active))
    if not svc:
        raise ToolError("service_not_found", f"Unknown service '{code}'.")
    return svc


def service_dict(s: Service) -> dict:
    return {"code": s.code, "name": s.name, "description": s.description,
            "price_inr": float(s.base_price_inr), "duration_min": s.duration_min}


def normalize_city(city: str) -> str:
    match = next((c for c in get_settings().supported_cities if c.lower() == city.strip().lower()), None)
    if not match:
        raise ToolError("city_not_supported",
                        f"We currently serve: {', '.join(get_settings().supported_cities)}.")
    return match
