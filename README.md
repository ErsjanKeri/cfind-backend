# CompanyFinder Albania - FastAPI Backend

Complete 1:1 replacement of Next.js backend with FastAPI Python backend for the CompanyFinder Albania platform.

## 🚀 Tech Stack

- **Framework**: FastAPI 0.109.0
- **Database**: PostgreSQL with SQLAlchemy (async)
- **Authentication**: JWT (RS256) with HTTPOnly cookies
- **Password Hashing**: Argon2id (production-grade)
- **File Storage**: AWS S3 / DigitalOcean Spaces
- **Email**: SendGrid
- **Migrations**: Alembic
- **Rate Limiting**: SlowAPI

## 📋 Prerequisites

- Python 3.11+
- PostgreSQL 15+
- OpenSSL (for generating JWT keys)

## ⚡ Quick Start

### 1. Clone and Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Generate JWT Keys

```bash
# Generate RS256 keypair (4096-bit RSA)
bash scripts/generate_jwt_keys.sh

# This creates:
# - keys/jwt_private.pem (keep secure!)
# - keys/jwt_public.pem
```

### 3. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your values
nano .env  # or your preferred editor
```

**Required environment variables:**

```env
# Database
DATABASE_URL=postgresql+asyncpg://companyfinder:password@localhost:5432/companyfinder

# JWT (generated keys)
JWT_PRIVATE_KEY_PATH=keys/jwt_private.pem
JWT_PUBLIC_KEY_PATH=keys/jwt_public.pem

# Email (SendGrid)
SENDGRID_API_KEY=your_sendgrid_api_key

# AWS S3 / DigitalOcean Spaces
AWS_REGION=eu-central-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_BUCKET_NAME=companyfinder-uploads
AWS_ENDPOINT=https://nyc3.digitaloceanspaces.com  # For DigitalOcean

# CORS (comma-separated)
CORS_ORIGINS=http://localhost:3000,https://companyfinder.al
```

### 4. Create Database

```bash
# Create PostgreSQL database
createdb companyfinder

# Or via psql:
psql -U postgres
CREATE DATABASE companyfinder;
\q
```

### 5. Run Migrations

```bash
# Generate initial migration
alembic revision --autogenerate -m "Initial schema"

# Apply migrations
alembic upgrade head
```

### 6. Start Development Server

```bash
# Run with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or use Python directly
python app/main.py
```

The API will be available at:
- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs (Swagger UI)
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## 🔐 Authentication Flow

### Phase 1 (Implemented)

1. **Register** → `POST /api/auth/register`
   - Creates user account (buyer or agent)
   - Sends verification email

2. **Verify Email** → `GET /api/auth/verify-email?token=...`
   - Verifies email address
   - Required before login

3. **Login** → `POST /api/auth/login`
   - Authenticates user
   - Issues JWT access token (15 min, HTTPOnly cookie)
   - Issues JWT refresh token (7-30 days, HTTPOnly cookie)
   - Issues CSRF token (non-HTTPOnly cookie for JS)

4. **Refresh Token** → `POST /api/auth/refresh`
   - Obtains new access token without re-authentication
   - Rate limited: 30/minute

5. **Logout** → `POST /api/auth/logout`
   - Revokes refresh token
   - Clears all cookies

6. **Password Reset** → `POST /api/auth/password-reset-request` + `POST /api/auth/password-reset`
   - Sends reset link to email
   - Rate limited: 3/hour
   - Single-use tokens (1-hour validity)

## 📚 API Endpoints

### Authentication (Phase 1 - ✅ Complete)

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|------------|
| POST | `/api/auth/register` | Register new user | 3/hour |
| GET | `/api/auth/verify-email` | Verify email with token | - |
| POST | `/api/auth/resend-verification` | Resend verification email | 3/hour |
| POST | `/api/auth/login` | Login user | 5/minute |
| POST | `/api/auth/refresh` | Refresh access token | 30/minute |
| POST | `/api/auth/logout` | Logout user | - |
| POST | `/api/auth/password-reset-request` | Request password reset | 3/hour |
| POST | `/api/auth/password-reset` | Reset password with token | - |

### Users (Phase 2 - ✅ Complete)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/users/me` | Get current user profile | ✅ |
| PUT | `/api/users/me` | Update user profile | ✅ + CSRF |
| POST | `/api/users/me/image` | Upload profile image | ✅ + CSRF |
| PUT | `/api/users/me/agent-profile` | Update agent profile | ✅ Agent + CSRF |
| PUT | `/api/users/me/buyer-profile` | Update buyer profile | ✅ Buyer + CSRF |
| GET | `/api/users/me/verification-status` | Get agent verification status | ✅ Agent |
| GET | `/api/users/me/documents` | Get agent document status | ✅ Agent |

### File Upload (Phase 2 - ✅ Complete)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/upload/presigned/image` | Get presigned URL for image | ✅ + CSRF |
| POST | `/api/upload/presigned/document` | Get presigned URL for document | ✅ Agent + CSRF |
| POST | `/api/upload/direct/image` | Direct image upload | ✅ + CSRF |
| POST | `/api/upload/direct/document` | Direct document upload | ✅ Agent + CSRF |
| POST | `/api/upload/document/confirm` | Confirm presigned document upload | ✅ Agent + CSRF |

### Coming in Future Phases

- **Listings**: CRUD, search, filter, public/private visibility (Phase 3)
- **Leads**: Buyer-agent interaction tracking (Phase 4)
- **Demands**: Buyer demand marketplace (Phase 5)
- **Promotions**: Credit system, listing promotion (Phase 6-7)
- **Admin**: User management, verification, analytics (Phase 8)
- **Cron**: Promotion expiration, currency updates (Phase 9)

## 🧪 Testing

### Manual Testing with cURL

**1. Register a buyer:**

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Buyer",
    "email": "buyer@example.com",
    "password": "SecurePass123",
    "role": "buyer"
  }'
```

**2. Register an agent:**

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Jane Agent",
    "email": "agent@example.com",
    "password": "SecurePass123",
    "role": "agent",
    "agency_name": "Best Properties",
    "license_number": "LIC123456",
    "phone": "+355691234567"
  }'
```

**3. Verify email** (get token from email/logs):

```bash
curl -X GET "http://localhost:8000/api/auth/verify-email?token=YOUR_TOKEN_HERE"
```

**4. Login:**

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{
    "email": "buyer@example.com",
    "password": "SecurePass123",
    "remember_me": false
  }'
```

**5. Access protected endpoint** (using cookies):

```bash
curl -X GET http://localhost:8000/api/users/me \
  -b cookies.txt
```

**6. Refresh token:**

```bash
curl -X POST http://localhost:8000/api/auth/refresh \
  -b cookies.txt \
  -c cookies.txt
```

**7. Logout:**

```bash
curl -X POST http://localhost:8000/api/auth/logout \
  -b cookies.txt \
  -H "X-CSRF-Token: YOUR_CSRF_TOKEN"
```

### Testing with Swagger UI

1. Go to http://localhost:8000/docs
2. Click "Authorize" button
3. Use registered credentials
4. Test all endpoints interactively

## 🗄️ Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history

# View current version
alembic current
```

## 🐳 Docker Deployment

### Using Docker Compose

```bash
# Build and start services
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down

# Rebuild after code changes
docker-compose up -d --build
```

### Environment Variables for Docker

Create `.env` file in backend directory with all required variables. Docker Compose will automatically load it.

## 📧 Email Configuration

### SendGrid Setup

1. Sign up at https://sendgrid.com
2. Create API key with "Mail Send" permissions
3. Add API key to `.env`:
   ```
   SENDGRID_API_KEY=SG.xxxxxxxxxxxxx
   ```

### Development Mode (No SendGrid)

If `SENDGRID_API_KEY` is not set:
- Emails will be logged to console
- Registration and password reset will work
- Check terminal logs for email content

## 🔑 Security Features

### Password Security
- **Argon2id** hashing with OWASP-recommended parameters
- Time cost: 2 iterations
- Memory cost: 64 MB
- Parallelism: 4 threads
- Automatic rehash when parameters change

### JWT Security
- **RS256 algorithm** (RSA with SHA-256)
- 4096-bit RSA keys
- Short-lived access tokens (15 minutes)
- Long-lived refresh tokens (7-30 days)
- Database-backed refresh tokens (revocation support)
- CSRF protection via double-submit cookie pattern

### HTTP Security
- HTTPOnly cookies (access & refresh tokens)
- Secure flag in production
- SameSite=lax for access token
- SameSite=strict for refresh token
- CORS with credential support

### Rate Limiting
- Registration: 3/hour per IP
- Login: 5/minute per IP
- Password reset: 3/hour per IP + 3/hour per user
- Token refresh: 30/minute per IP
- Verification resend: 3/hour per IP

## 🛠️ Development

### Project Structure

```
backend/
├── app/
│   ├── api/              # API routes & dependencies
│   │   ├── routes/       # Endpoint handlers
│   │   └── deps.py       # Auth dependencies
│   ├── core/             # Core utilities
│   │   ├── security.py   # JWT, password hashing
│   │   ├── constants.py  # Enums, constants
│   │   └── exceptions.py # Custom exceptions
│   ├── models/           # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic validation schemas
│   ├── services/         # Business logic
│   ├── repositories/     # Data access layer (TODO)
│   ├── db/               # Database setup
│   ├── utils/            # Helper utilities
│   ├── config.py         # Settings
│   └── main.py           # FastAPI app
├── alembic/              # Database migrations
├── scripts/              # Utility scripts
├── keys/                 # JWT keys (gitignored)
└── requirements.txt      # Python dependencies
```

### Code Style

- Follow PEP 8
- Type hints for all function parameters and returns
- Docstrings for all modules, classes, and functions
- Maximum line length: 120 characters

### Adding New Routes

1. Create route file in `app/api/routes/`
2. Define Pydantic schemas in `app/schemas/`
3. Create business logic in `app/services/`
4. Register router in `app/main.py`

## 📊 Monitoring

### Logs

- **Development**: INFO level, detailed logs
- **Production**: WARNING level, minimal logs

### Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "environment": "development",
  "service": "CompanyFinder Albania API"
}
```

## 🚨 Troubleshooting

### JWT Keys Not Found

```bash
# Generate keys
bash scripts/generate_jwt_keys.sh

# Verify keys exist
ls -la keys/
```

### Database Connection Error

```bash
# Check PostgreSQL is running
pg_isready

# Verify DATABASE_URL in .env
echo $DATABASE_URL

# Test connection
psql $DATABASE_URL
```

### Migration Issues

```bash
# Reset migrations (⚠️ DESTRUCTIVE - development only)
alembic downgrade base
alembic upgrade head

# Or drop and recreate database
dropdb companyfinder
createdb companyfinder
alembic upgrade head
```

### Email Not Sending

- Check `SENDGRID_API_KEY` in `.env`
- Verify API key has "Mail Send" permission
- Check logs for SendGrid errors
- In development, emails are logged to console

## 📝 License

Copyright © 2024 CompanyFinder Albania. All rights reserved.

## 🤝 Contributing

This is a private project. For questions or issues, contact the development team.

---

**Status**: Phase 2 Complete ✅
- ✅ Authentication (register, login, email verification, password reset)
- ✅ User management (profile CRUD, image upload, agent re-verification)
- ✅ File uploads (S3 presigned URLs, direct uploads, document management)
- ⏳ Listings system (coming in Phase 3)
- ⏳ Leads & saved listings (coming in Phase 4)
- ⏳ Buyer demands (coming in Phase 5)
- ⏳ Promotion system (coming in Phase 6-7)
- ⏳ Admin panel (coming in Phase 8)

For detailed implementation plan, see [Implementation Plan](/.claude/plans/hashed-popping-wigderson.md)
