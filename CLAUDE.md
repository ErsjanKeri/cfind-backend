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

## Buyer Demands (Reverse Marketplace)

Buyers post what they're looking for; verified agents browse and claim demands.

### Workflow
1. Buyer creates demand (status: `active`) with budget, category, city, description
2. Verified agents browse active demands via `GET /demands`
3. Agent claims demand → status becomes `assigned` (exclusive, first-claimer wins via atomic UPDATE with WHERE status='active')
4. Email sent to buyer with agent contact info
5. Buyer marks as `fulfilled` or `closed`

### Deletion rules
Only `active` demands can be deleted. Assigned/fulfilled/closed demands are kept for historical tracking.

### Key files
- `app/api/routes/demands.py`, `app/repositories/demand_repo.py`, `app/schemas/demand.py`, `app/models/demand.py`

## Promotion & Credits System

Agents purchase credits and spend them to promote listings to higher visibility tiers.

### Tiers
- `standard` (free, default) → `featured` (5 credits/30 days) → `premium` (15 credits/30 days)
- Upgrading from featured→premium charges only the difference (10 credits)
- Listing search always sorts by tier priority (premium > featured > standard), then secondary sort

### Credit flow
- `create_credit_transaction()` in `promotion_repo.py` atomically updates `AgentProfile.credit_balance` using a WHERE clause to prevent negative balance race conditions
- Transaction types: `purchase`, `usage`, `refund`, `bonus`, `adjustment`
- Payments are currently **simulated** (TODO: Stripe/PayPal integration)

### Expiration
- Cron endpoint `POST /cron/expire-promotions` marks expired promotions and resets listing tiers
- `PromotionHistory` tracks performance metrics: `views_during_promotion`, `leads_during_promotion`

### Key files
- `app/api/routes/promotions.py`, `app/repositories/promotion_repo.py`, `app/models/promotion.py`, `app/schemas/promotion.py`

## Geography System

DB-backed countries, cities, and neighbourhoods. Admin-managed via `POST/PUT/DELETE /admin/geography/...`.

### Important caveat
`VALID_COUNTRY_CODES` in `app/core/constants.py` is hardcoded `["al", "ae"]`. Multiple routes validate against this constant. If countries are added to the DB, the constant must also be updated. Agent service system prompts and tool enum declarations also hardcode country lists.

### Key files
- `app/api/routes/countries.py` (public read), `app/repositories/geography_repo.py`, `app/models/country.py`, `app/schemas/geography.py`
- Admin geography endpoints in `app/api/routes/admin.py`

## AI Agent (Chat)

The AI agent lives in `app/services/agent_service.py` and is accessed via `app/api/routes/chat.py` (prefix `/chat`).

### Two modes
- **Buyer mode**: Listing recommendations only. Tools: `search_listings`, `get_listing_detail`, `get_market_info`. User context includes country preference + saved listing titles. **By design, buyer mode has NO access to the demands system** — buyers discover listings through AI search, and agents are the ones who connect buyers to opportunities. The demand system is agent-facing only.
- **Agent mode**: Demand matching. Tools: `search_demands`, `get_demand_detail`, `search_my_listings`, `get_market_info`. Helps agents find buyer demands that match their listings. Agents are the connectors between buyer demands and available businesses.

### How it works
- Uses Gemini function calling. Tool calls execute real DB queries, results fed back to Gemini for conversational response.
- Tool call results stored in `tool_calls` JSON column on messages so frontend can render listing/demand cards.
- Separate system prompts and tool declarations per mode (`SYSTEM_INSTRUCTION` / `AGENT_SYSTEM_INSTRUCTION`).
- Max 5 tool-call rounds per message. Rate limited 6/minute + daily message limit.

### Key files
- `app/services/agent_service.py` — Gemini client, tool declarations, tool executors, chat loop
- `app/api/routes/chat.py` — REST endpoints (POST `/message`, GET/DELETE `/conversations`)
- `app/repositories/chat_repo.py` — Conversation/Message CRUD
- `app/models/conversation.py` — Conversation + Message SQLAlchemy models

### Access control
- All three roles (`buyer`, `agent`, `admin`) can access chat. Mode must match role (buyer mode for buyers, agent mode for agents, admin can use either).
- State-changing endpoints require CSRF token
- Daily message limit: `AGENT_MAX_MESSAGES_PER_DAY` (default: 50)

### Known issues
- No known issues in agent service at this time.

### Config
- `GEMINI_API_KEY` — Google AI API key (required, set as SECRET in DigitalOcean)
- `GEMINI_MODEL` — Model name (default: `gemini-2.5-flash`)
- `AGENT_MAX_MESSAGES_PER_DAY` — Daily user message limit (default: 50)