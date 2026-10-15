"""python -m scripts.make_admin you@example.com"""
import sys
from sqlalchemy import update
from app.db.models import Customer
from app.db.session import SessionLocal

with SessionLocal() as db:
    n = db.execute(update(Customer).where(Customer.email == sys.argv[1].lower()).values(is_admin=True)).rowcount
    db.commit()
    print("updated" if n else "no such customer")
