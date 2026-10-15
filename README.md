# OmniAssist AI

**An omnichannel AI customer-support assistant with grounded answers,
appointment booking, and voice-enabled interactions.**

OmniAssist AI is a full-stack prototype for **QuickCare India**, a
fictional home-services business. Customers can ask questions about
services and policies, receive answers grounded in company documents,
check service availability, and manage appointment requests through a
web interface. The application also includes conversation history, human
handoff, and voice-interaction components.

> **Project status:** Local development prototype. AI responses depend
> on the configured Gemini model/API availability. Use test data while
> developing.

## Highlights

-   **Document-grounded Q&A (RAG):** Ingests service, FAQ, warranty, and
    cancellation-policy documents and retrieves relevant passages for
    answers.
-   **Source citations:** Answers can include document names, sections,
    and supporting snippets.
-   **Safer unknown-answer behavior:** When relevant information is not
    found, the assistant can abstain rather than inventing an answer.
-   **Service catalogue:** Displays service descriptions, prices in INR,
    and estimated durations.
-   **Appointment workflow:** Checks availability, proposes an
    appointment, and supports confirmation and cancellation.
-   **Authentication:** Customer registration and login with token-based
    authentication.
-   **Conversation history:** Stores conversations and messages for
    later retrieval.
-   **Human handoff:** Supports escalating a conversation to a human
    agent.
-   **Voice UI:** Includes a voice interaction hook/interface; available
    behavior depends on browser permissions and configuration.
-   **Admin analytics:** Provides an endpoint for application analytics.
-   **Responsive web interface:** React, TypeScript, and Vite frontend.

## Tech stack

  Layer               Technologies
  ------------------- ------------------------------------------
  Frontend            React, TypeScript, Vite, CSS
  Backend API         Python, FastAPI, Uvicorn
  Database            PostgreSQL, SQLAlchemy
  Migrations          Alembic
  Retrieval           Document chunking, embeddings, pgvector
  Generative AI       Google Gemini API
  Configuration       Pydantic Settings, environment variables
  API documentation   FastAPI / OpenAPI / Swagger UI

## Architecture

``` text
Customer
   |
   v
React + TypeScript frontend (Vite)
   |
   | HTTP / JSON + bearer token
   v
FastAPI backend
   |---- Authentication
   |---- Chat and conversation history
   |---- RAG retrieval and citations ----> Documents + embeddings
   |---- Services and availability
   |---- Appointment workflow
   |---- Human handoff and analytics
   |
   v
PostgreSQL (Supabase or local PostgreSQL)
   |
   +---- Gemini API for model/embedding operations
```

## Repository structure

``` text
omniassist/
├── backend/
│   ├── app/
│   │   ├── core/          # Settings and shared configuration
│   │   ├── db/            # Database session and models
│   │   ├── rag/           # Document ingestion and retrieval
│   │   ├── tools/         # Service-related operations
│   │   └── ...            # FastAPI routes and application modules
│   ├── alembic/           # Database migrations
│   ├── scripts/
│   │   └── seed.py         # Seed service catalogue and technicians
│   └── pyproject.toml
├── data/
│   └── documents/         # Knowledge-base Markdown documents
├── frontend/
│   ├── src/
│   │   ├── Admin.tsx
│   │   ├── App.tsx
│   │   ├── Bookings.tsx
│   │   ├── Chat.tsx
│   │   ├── Login.tsx
│   │   ├── api.ts
│   │   ├── styles.css
│   │   └── useVoice.ts
│   ├── package.json
│   └── vite.config.ts
├── tests/
├── eval/
├── .env.example
└── README.md
```

## Prerequisites

-   Python 3.11+ recommended (the current development environment has
    also been tested with Python 3.13).
-   Node.js and npm.
-   A PostgreSQL database. Supabase PostgreSQL is supported by the
    current configuration.
-   A Google Gemini API key for AI and embedding features.
-   Git (optional, for version control).

## Setup on Windows

Run commands from **Command Prompt** unless otherwise noted. Replace
paths and values with your own environment settings.

### 1. Clone or open the project

``` cmd
git clone <your-repository-url>
cd omniassist
```

If you already have the project locally, open its root folder in VS Code
instead.

### 2. Create and activate a Python virtual environment

``` cmd
python -m venv .venv
.venv\Scripts\activate
```

### 3. Configure environment variables

Create your local `.env` from the example:

``` cmd
copy .env.example .env
```

Edit `.env` locally and set your database URL, Gemini API key, and a
strong JWT secret. **Never commit `.env` or paste credentials, API keys,
database passwords, or bearer tokens into public issues.**

Example shape only---replace every placeholder with your own values:

``` env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
GEMINI_API_KEY=your_gemini_api_key
JWT_SECRET=replace_with_a_long_random_secret
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIM=768
LLM_MODEL=gemini-2.5-flash
RAG_TOP_K=5
RAG_MIN_SIMILARITY=0.55
CORS_ORIGINS=["http://localhost:5173"]
```

Keep the remaining settings from `.env.example` unless you know you need
to change them. If your database password contains URL-reserved
characters, URL-encode it in `DATABASE_URL`.

### 4. Install backend dependencies

``` cmd
cd backend
python -m pip install --upgrade pip
pip install -e .
```

If your project environment uses a different install workflow, follow
the dependency instructions in `backend/pyproject.toml`.

### 5. Apply database migrations

From the `backend` directory:

``` cmd
alembic upgrade head
alembic current
```

The current database revision should report the migration head.

### 6. Seed services and technicians

From the `backend` directory:

``` cmd
python -m scripts.seed
```

The seed script is designed to add missing service and technician
records. Review the script before running it against a database that
already contains production data.

### 7. Start the backend

From the `backend` directory:

``` cmd
uvicorn app.main:app --reload
```

Useful local URLs:

-   API: `http://127.0.0.1:8000`
-   Swagger UI: `http://127.0.0.1:8000/docs`
-   OpenAPI schema: `http://127.0.0.1:8000/openapi.json`
-   Health endpoint: `http://127.0.0.1:8000/health`

Keep this terminal open while using the frontend.

### 8. Ingest the knowledge-base documents

Open a second terminal, activate the virtual environment, and run:

``` cmd
cd /d <path-to-project>\backend
python -m app.rag.ingest "E:\projects\omniassist\data\documents"
```

Replace the example path with the actual absolute path to your project's
`data\documents` directory. The ingestion command should report the
documents/chunks it processes. Re-run ingestion when you update
knowledge-base documents.

### 9. Install and start the frontend

Open another terminal:

``` cmd
cd /d <path-to-project>\frontend
npm install
npm run dev
```

Open the local URL printed by Vite (commonly `http://localhost:5173`).
Keep the backend and frontend terminals running.

If the frontend uses a Vite environment variable for the backend URL,
inspect `frontend/.env.example` and configure it in a local
`frontend/.env` file as documented by the project. Do not put secret API
keys in frontend environment variables.

## API overview

The FastAPI Swagger page at `/docs` is the authoritative place to
inspect request schemas and required fields. The application currently
exposes routes in these areas:

  -------------------------------------------------------------------------------------
  Method                  Endpoint                              Purpose
  ----------------------- ------------------------------------- -----------------------
  `POST`                  `/auth/register`                      Register a customer

  `POST`                  `/auth/login`                         Authenticate and obtain
                                                                a token

  `GET`                   `/me`                                 Retrieve the
                                                                authenticated user's
                                                                profile

  `GET`                   `/services`                           List active services

  `GET`                   `/availability`                       Check available
                                                                appointment slots

  `POST`                  `/appointments/propose`               Propose/hold an
                                                                appointment

  `POST`                  `/appointments/{appt_id}/confirm`     Confirm an appointment

  `POST`                  `/appointments/{appt_id}/cancel`      Cancel an appointment

  `GET`                   `/appointments`                       List the current user's
                                                                appointments

  `POST`                  `/chat/ask`                           Ask a knowledge-base
                                                                question and receive
                                                                citations

  `GET`                   `/conversations`                      List conversations

  `GET`                   `/conversations/{conv_id}/messages`   Retrieve messages in a
                                                                conversation

  `POST`                  `/chat/message`                       Send a message through
                                                                the chat workflow

  `POST`                  `/conversations/{conv_id}/handoff`    Request a human-agent
                                                                handoff

  `GET`                   `/admin/analytics`                    Retrieve admin
                                                                analytics
  -------------------------------------------------------------------------------------

Some endpoints require authentication. Use Swagger's **Authorize**
control after logging in, and use the schemas shown there rather than
assuming example request fields.

## Knowledge-base documents

The current knowledge base includes Markdown documents such as:

-   `services_and_pricing.md`
-   `faq.md`
-   `cancellation_policy.md`
-   `warranty_policy.md`

The RAG flow chunks the documents, creates embeddings, retrieves
relevant chunks, and returns source references with answers when
supporting information is available. Keep documents clear, factual, and
updated; re-ingest them after edits.

## Testing checklist

-   [ ] `GET /health` responds successfully.
-   [ ] Swagger UI loads at `/docs`.
-   [ ] Customer registration and login work.
-   [ ] `GET /services` returns the seeded service catalogue.
-   [ ] `GET /availability` returns slots for a supported service, city,
    and date.
-   [ ] An appointment can be proposed and confirmed using the exact
    request schema in Swagger.
-   [ ] A question about service prices returns a grounded answer with
    citations.
-   [ ] An unsupported question does not produce invented facts.
-   [ ] The frontend loads and can sign in to the API.
-   [ ] Chat history and appointments load in the frontend.
-   [ ] Human handoff behavior is verified.
-   [ ] Temporary Gemini/API errors show a useful fallback instead of
    misleading success.

## Troubleshooting

### Gemini returns `503 UNAVAILABLE`

This can be a temporary model-capacity issue. Retry after a short delay.
If it continues, check the Google AI service status, API quota/limits,
and configured model. The app should gracefully handle repeated failures
and avoid presenting an unsuccessful AI response as a successful answer.

### Database connection fails

-   Verify the database host, port, username, password, and database
    name in `.env`.
-   Confirm the database accepts connections from your network.
-   For Supabase, use the connection string appropriate to your network
    and pooler/direct-connection setup.
-   URL-encode reserved characters in the database password.
-   Never share the full connection string in screenshots or logs.

### Services list is empty

Run the seed command from the `backend` directory:

``` cmd
python -m scripts.seed
```

Then retry `GET /services` in Swagger.

### RAG cannot find relevant information

-   Confirm that the documents exist under `data/documents`.
-   Run the ingestion command with the correct absolute path.
-   Check the backend terminal for embedding or database errors.
-   Ask a question that is clearly covered by the documents.

### Frontend cannot reach the backend

-   Confirm the API is running at `http://127.0.0.1:8000`.
-   Check the frontend's API base URL in `frontend/src/api.ts` and its
    environment example.
-   Check CORS configuration in `.env`.
-   Inspect browser DevTools and the backend terminal for errors.

## Security notes

-   Keep `.env`, API keys, database credentials, JWT secrets, and bearer
    tokens out of Git.
-   Use a unique, strong JWT secret outside local development.
-   Do not use example/test passwords for real accounts.
-   Use HTTPS and secure deployment configuration before exposing the
    app publicly.
-   Add rate limiting, robust authorization checks, input validation,
    logging hygiene, and appropriate retention policies before
    production use.
-   Use fictional/test customer data during development.

## Roadmap

-   Improve retries, timeouts, and fallback behavior for transient LLM
    failures.
-   Polish responsive chat UX and citation presentation.
-   Complete end-to-end voice interaction and interruption handling.
-   Improve appointment-flow validation and confirmation feedback.
-   Expand automated tests for RAG quality, booking logic, and
    authentication.
-   Add production deployment, monitoring, and CI checks.

## Contributing

1.  Create a feature branch.
2.  Make a focused change.
3.  Run the relevant tests and manually verify the affected workflow.
4.  Keep credentials and local environment files out of commits.
5.  Submit a pull request with a concise description and test notes.

## License

Add a license file and update this section before distributing the
project publicly. No license is specified here.
