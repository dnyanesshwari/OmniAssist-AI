"""Seed services + technicians (idempotent). Usage: python -m scripts.seed"""
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.models import Service, Technician, TechnicianService
from app.db.session import SessionLocal

SERVICES = [  # code, name, price INR, minutes, description
    ("ac_service", "AC Service & Cleaning", 599, 60, "Jet-wash cleaning of indoor and outdoor unit, gas pressure check."),
    ("ac_repair", "AC Repair", 499, 60, "Diagnosis and repair of cooling, leakage or noise issues. Parts extra."),
    ("plumbing", "Plumbing Repair", 349, 60, "Leaks, taps, flush tanks, blockages. Parts extra."),
    ("electrician", "Electrician Visit", 299, 30, "Switches, fans, wiring faults, MCB issues. Parts extra."),
    ("appliance_repair", "Washing Machine / Fridge Repair", 449, 60, "Diagnosis and repair of home appliances. Parts extra."),
    ("deep_cleaning", "Home Deep Cleaning", 2499, 180, "Full-home deep cleaning for up to 2 BHK."),
    ("pest_control", "Pest Control", 1299, 90, "Odourless gel and spray treatment for cockroaches, ants and bed bugs."),
]
TECH_SKILLS = [  # which services each of the 3 techs per city covers
    [s[0] for s in SERVICES],
    ["ac_service", "ac_repair", "plumbing", "electrician", "appliance_repair"],
    ["deep_cleaning", "pest_control"],
]


def seed(db: Session) -> None:
    by_code = {}
    for code, name, price, mins, desc in SERVICES:
        svc = db.scalar(select(Service).where(Service.code == code))
        if not svc:
            svc = Service(code=code, name=name, description=desc,
                          base_price_inr=Decimal(price), duration_min=mins)
            db.add(svc)
        by_code[code] = svc
    db.flush()
    for city in get_settings().supported_cities:
        for i, skills in enumerate(TECH_SKILLS, start=1):
            name = f"{city} Tech {i}"
            tech = db.scalar(select(Technician).where(Technician.name == name))
            if not tech:
                tech = Technician(name=name, city=city)
                db.add(tech)
                db.flush()
                db.add_all(TechnicianService(technician_id=tech.id, service_id=by_code[c].id) for c in skills)
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db)
    print("seeded")
