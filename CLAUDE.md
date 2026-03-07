# Rules

- Work in small chunks. Think first, ask first if unclear.
- NEVER over-engineer. Simplest solution first.
- ALWAYS read existing files before modifying. Check how similar things are already done.
- Follow existing patterns — don't invent new ones.
- Prefer editing existing files over creating new ones.
- Do not write tests unless explicitly asked.
- Do not generate or modify Alembic migrations unless explicitly asked.
- Do not touch the scripts/ folder unless explicitly asked.
- Only commit/push when explicitly told to.
- Do not add section divider comments (the # ==== blocks). Keep comments minimal — only where logic isn't self-evident.

# Architecture

- Routes (`app/api/routes/`) call repos (`app/repositories/`) directly. No service layer in between.
- Services (`app/services/`) are only for cross-cutting concerns: email, file uploads.
- Models in `app/models/`, Pydantic schemas in `app/schemas/`.
- Auth dependencies in `app/api/deps.py` — chained: get_current_user → get_verified_user → get_verified_agent.
- Config via pydantic-settings in `app/config.py`. Single `settings` instance.
- Async SQLAlchemy throughout. Session from `app/db/session.py` via `Depends(get_db)`.
- Repos return tuples of (model, related_model) for listings/leads. Transform functions convert to public/private schemas.

# Stack

- Python 3.11, FastAPI, SQLAlchemy (async), PostgreSQL, Alembic
- Auth: RS256 JWT (cookie-based), CSRF double-submit, Argon2 passwords
- Storage: DigitalOcean Spaces (S3-compatible, boto3)
- Email: ZeptoMail via SMTP
- Deploy: DigitalOcean App Platform (Dockerfile, auto-deploy on push to main)
