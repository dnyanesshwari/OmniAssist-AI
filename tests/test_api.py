from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def register(client, email):
    r = client.post("/auth/register", json={"email": email, "name": "T", "password": "password123"})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_auth_required(client):
    assert client.get("/appointments").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_register_login_duplicate(client):
    register(client, "a@example.com")
    assert client.post("/auth/register", json={"email": "a@example.com", "name": "T",
                                                "password": "password123"}).status_code == 409
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "wrong-pass"}).status_code == 401
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "password123"}).status_code == 200


def test_booking_flow_and_isolation(client, seeded):
    a, b = register(client, "a@example.com"), register(client, "b@example.com")
    start = (datetime.now(IST) + timedelta(days=3)).replace(hour=12, minute=0, second=0, microsecond=0)
    body = {"service_code": "plumbing", "city": "Mumbai", "start_at": start.isoformat(),
            "address": "5 Marine Drive, Mumbai", "idempotency_key": "api-key-0001"}
    r = client.post("/appointments/propose", json=body, headers=a)
    assert r.status_code == 201
    aid = r.json()["appointment"]["id"]
    # other customer: 404, and list is empty
    assert client.post(f"/appointments/{aid}/confirm", headers=b).status_code == 404
    assert client.get("/appointments", headers=b).json() == []
    assert client.post(f"/appointments/{aid}/confirm", headers=a).json()["appointment"]["status"] == "booked"
    # cancel preview does not cancel
    p = client.post(f"/appointments/{aid}/cancel", json={"confirmed": False}, headers=a).json()
    assert p["requires_confirmation"]
    assert client.get("/appointments", headers=a).json()[0]["status"] == "booked"


def test_validation_errors_are_422(client, seeded):
    a = register(client, "a@example.com")
    r = client.post("/appointments/propose", headers=a, json={
        "service_code": "plumbing", "city": "Mumbai", "start_at": "2020-01-01T10:00:00+05:30",
        "address": "5 Marine Drive", "idempotency_key": "api-key-0002"})
    assert r.status_code == 422 and r.json()["detail"]["error"] == "too_soon"


def test_conversation_isolation(client, seeded, fake_gemini, db):
    from app.rag.ingest import ingest_dir
    from app.core.config import get_settings
    ingest_dir(db, get_settings().docs_dir)
    a, b = register(client, "a@example.com"), register(client, "b@example.com")
    r = client.post("/chat/ask", json={"question": "what is the cancellation charge?"}, headers=a).json()
    cid = r["conversation_id"]
    assert r["citations"]
    assert client.get(f"/conversations/{cid}/messages", headers=a).status_code == 200
    assert client.get(f"/conversations/{cid}/messages", headers=b).status_code == 404
    assert client.post("/chat/ask", json={"question": "hello?", "conversation_id": cid}, headers=b).status_code == 404
