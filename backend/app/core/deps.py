from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.core.security import decode_token
from app.db.models import Customer
from app.db.session import get_db

bearer = HTTPBearer(auto_error=False)


def current_customer(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Customer:
    cid = decode_token(creds.credentials) if creds else None
    customer = db.get(Customer, cid) if cid else None
    if not customer:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing token")
    return customer
