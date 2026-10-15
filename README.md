# OmniAssist AI — Steps 1–2 (Backend, RAG, Tools, Agent, Voice, Frontend)

## Run (no Docker)
```bash
# 1. Postgres with pgvector + btree_gist (local install, or Neon/Supabase)
cp .env.example .env            # edit DATABASE_URL, GEMINI_API_KEY, JWT_SECRET (.env at repo root is fine)

# 2. backend (run everything from backend/)
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
python -m scripts.seed
python -m app.rag.ingest ../data/documents
uvicorn app.main:app --reload --port 8000             # docs: http://localhost:8000/docs

# 3. frontend (new terminal)
cd frontend && npm install && npm run dev             # http://localhost:5173
```
Docker files (`docker-compose.yml`, Dockerfiles) are optional and not needed for local runs.

## Try it
```bash
TOKEN=$(curl -s localhost:8000/auth/register -H 'content-type: application/json' \
  -d '{"email":"me@example.com","name":"Me","password":"password123"}' | python -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -s localhost:8000/chat/ask -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"question":"What is the cancellation charge 1 hour before my appointment?"}'
```

## Tests (needs local Postgres with pgvector; Gemini is faked)
```bash
createdb omniassist_test        # or use the compose db
export TEST_DATABASE_URL=postgresql+psycopg://omni:change_me@localhost:5432/omniassist_test
pip install -e "backend[dev]" && pytest
```

## Design notes
- Booking is two-phase: `propose` holds a slot (10 min), `confirm` books it. Cancel previews the fee until `confirmed=true`.
- Race safety: Postgres EXCLUDE constraint (btree_gist) prevents a technician being double-booked; verified by a 6-thread race test.
- Idempotency: `(customer_id, idempotency_key)` unique; replays return the original result.
- RAG abstains when similarity is below `RAG_MIN_SIMILARITY` or the answer lacks valid `[n]` citations.

## Step 2 additions
```bash
cd backend && python -m scripts.make_admin you@example.com   # enables the Analytics tab
# UI: http://localhost:5173 (Chrome/Edge recommended for browser speech recognition)
```
- **Agent** (`backend/app/agent`): LangGraph `guard → pending → classify → {policy|availability|book|cancel|list|other} → handoff`.
  The LLM only classifies intent and extracts slots. Booking/cancel side effects run only after a strict yes/no gate in code
  (`guards.parse_yes_no`); "yes but 5pm" never confirms. Customer id always comes from the auth token.
- **Handoff**: sensitive-complaint keywords, explicit human requests, 3 consecutive failures/abstentions. The summary is built
  deterministically from stored data (works even when Gemini is down).
- **Voice** (`/ws/voice`): partial/final transcripts, barge-in (`interrupt` cancels the in-flight turn; its result is discarded),
  idle prompt then close after `VOICE_IDLE_SECONDS`, optional server ASR (`audio.chunk`/`audio.end`) and server TTS.
- **Demo outage**: set `ALLOW_FAILURE_INJECTION=true`, tick "Simulate AI outage" in the chat footer.

## Known limitations (so far)
- Gemini ASR/TTS and the live Gemini classifier are untested here (fakes used in tests); browser speech recognition is untested in CI.
- With speakers (no headphones) the browser can hear its own TTS and self-interrupt.
- A cancelled voice turn may leave a 10-minute slot hold behind; it expires on its own.
