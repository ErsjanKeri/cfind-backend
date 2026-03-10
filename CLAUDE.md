# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
# Run dev server (auto-reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run migrations
alembic upgrade head

# Create migration (only when explicitly asked)
alembic revision --autogenerate -m "Description"

# Install dependencies
pip install -r requirements.txt

# Run a single test
pytest test_file.py -v

# API docs (dev only): http://localhost:8000/docs
```

## Rules

- Work in small chunks. Think first, ask first if unclear.
- NEVER over-engineer. Simplest solution first.
- ALWAYS read existing files before modifying. Check how similar things are already done.
- Follow existing patterns — don't invent new ones.
- Prefer editing existing files over creating new ones.
- Do not write tests unless explicitly asked.
- Do not generate or modify Alembic migrations unless explicitly asked.
- Do not touch the `scripts/` folder unless explicitly asked.
- Only commit/push when explicitly told to.
- Do not add section divider comments (the `# ====` blocks). Keep comments minimal — only where logic isn't self-evident.

## Architecture

### Request Flow
Routes (`app/api/routes/`) call repos (`app/repositories/`) directly. **No service layer in between.**

Services (`app/services/`) exist only for cross-cutting concerns: email (`email_service.py`), file uploads (`upload_service.py`), AI agent (`agent_service.py`).

### Auth Dependency Chain
Dependencies in `app/api/deps.py` chain in order:
- `get_current_user` — extracts JWT from cookie, fetches fresh user from DB
- `get_verified_user` — adds email verification check
- `get_verified_agent` — adds agent approval + document check (admins bypass)
- `verify_csrf_token` — double-submit cookie pattern for state-changing operations
- `RoleChecker(["role1", "role2"])` — role-based access control factory
- `get_current_user_optional` — returns `None` instead of 401 for anonymous access
- `ensure_owner_or_admin()` — utility function (not a dependency), checks resource ownership

### Data Layer
- Models in `app/models/` (SQLAlchemy ORM, UUID primary keys)
- Pydantic schemas in `app/schemas/` — all response schemas inherit from `BaseSchema` (`app/schemas/base.py`) which enables `from_attributes` and auto-coerces UUIDs to strings
- Repos return tuples of `(model, related_model)` for listings/leads. Transform functions in repos (e.g., `transform_public_listing`, `transform_private_listing`) convert to public/private schemas.
- Async SQLAlchemy throughout. Session via `Depends(get_db)` from `app/db/session.py`. Session auto-commits on success, rolls back on exception.

### Config
- `app/config.py` — pydantic-settings `Settings` class, single `settings` instance. JWT keys loaded at module level as `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY`.
- Constants/enums in `app/core/constants.py`
- Custom HTTP exceptions in `app/core/exceptions.py`
- Security utilities (JWT encode/decode, password hashing) in `app/core/security.py`

### Routers
All routers registered in `app/main.py` with `prefix=settings.API_PREFIX` (`/api`). Each route file defines its own sub-prefix (e.g., `/listings`, `/leads`).

## Stack

- Python 3.11, FastAPI, SQLAlchemy (async), PostgreSQL, Alembic
- Auth: RS256 JWT (cookie-based), CSRF double-submit, Argon2 passwords
- Storage: DigitalOcean Spaces (S3-compatible, boto3) via `app/utils/s3_client.py`
- Email: ZeptoMail via SMTP
- Rate limiting: SlowAPI
- AI: Google Gemini 2.5 Flash via `google-genai` SDK (function calling for listing search)
- Deploy: DigitalOcean App Platform (Dockerfile, auto-deploy on push to main)

## AI Agent (Chat)

The AI recommendation agent lives in `app/services/agent_service.py` and is accessed via `app/api/routes/chat.py` (prefix `/chat`).

### How it works
- Uses Gemini function calling with 3 tool declarations: `search_listings`, `get_listing_detail`, `get_market_info`
- Tool calls execute real DB queries against the Listing model, then results are fed back to Gemini for a conversational response
- Tool call results (including listing data) are stored in the `tool_calls` JSON column on messages so the frontend can render listing cards
- User context (country preference + saved listing titles) is injected into the system prompt for personalized recommendations

### Key files
- `app/services/agent_service.py` — Gemini client, tool declarations, tool executors, chat loop
- `app/api/routes/chat.py` — REST endpoints (POST `/message`, GET/DELETE `/conversations`)
- `app/repositories/chat_repo.py` — Conversation/Message CRUD
- `app/models/conversation.py` — Conversation + Message SQLAlchemy models
- `app/schemas/chat.py` — Pydantic request/response schemas

### Access control
- Restricted to `buyer` and `admin` roles via `RoleChecker(["buyer", "admin"])`
- State-changing endpoints (send message, delete conversation) require CSRF token
- Daily message limit configured via `AGENT_MAX_MESSAGES_PER_DAY` setting

### Config
- `GEMINI_API_KEY` — Google AI API key (required, set as SECRET in DigitalOcean)
- `GEMINI_MODEL` — Model name (default: `gemini-2.5-flash`)
- `AGENT_MAX_MESSAGES_PER_DAY` — Daily user message limit (default: 50)