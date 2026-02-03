#!/bin/bash

# Quick setup script for CompanyFinder Albania FastAPI Backend
# Automates: venv creation, dependency installation, JWT key generation, database setup

set -e  # Exit on error

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 CompanyFinder Albania - FastAPI Backend Setup${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Step 1: Check Python version
echo -e "${BLUE}1️⃣  Checking Python version...${NC}"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED_VERSION="3.11"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}❌ Python 3.11+ required. Found: $PYTHON_VERSION${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Python $PYTHON_VERSION${NC}"
echo ""

# Step 2: Check PostgreSQL
echo -e "${BLUE}2️⃣  Checking PostgreSQL...${NC}"
if ! command -v psql &> /dev/null; then
    echo -e "${YELLOW}⚠️  PostgreSQL client not found. Please install PostgreSQL 15+${NC}"
else
    PG_VERSION=$(psql --version | awk '{print $3}')
    echo -e "${GREEN}✅ PostgreSQL $PG_VERSION${NC}"
fi
echo ""

# Step 3: Create virtual environment
echo -e "${BLUE}3️⃣  Creating Python virtual environment...${NC}"
if [ -d "venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment already exists${NC}"
else
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
fi
echo ""

# Step 4: Activate and install dependencies
echo -e "${BLUE}4️⃣  Installing dependencies...${NC}"
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}✅ Dependencies installed${NC}"
echo ""

# Step 5: Generate JWT keys
echo -e "${BLUE}5️⃣  Generating JWT keys...${NC}"
if [ -f "keys/jwt_private.pem" ] && [ -f "keys/jwt_public.pem" ]; then
    echo -e "${YELLOW}⚠️  JWT keys already exist${NC}"
else
    bash scripts/generate_jwt_keys.sh
    echo -e "${GREEN}✅ JWT keys generated${NC}"
fi
echo ""

# Step 6: Setup environment file
echo -e "${BLUE}6️⃣  Setting up environment configuration...${NC}"
if [ -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file already exists${NC}"
else
    cp .env.example .env
    echo -e "${GREEN}✅ .env file created from template${NC}"
    echo -e "${YELLOW}⚠️  IMPORTANT: Edit .env with your actual credentials${NC}"
fi
echo ""

# Step 7: Create database
echo -e "${BLUE}7️⃣  Database setup...${NC}"
read -p "   Create PostgreSQL database 'companyfinder'? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if createdb companyfinder 2>/dev/null; then
        echo -e "${GREEN}✅ Database 'companyfinder' created${NC}"
    else
        echo -e "${YELLOW}⚠️  Database might already exist or creation failed${NC}"
        echo "   Run manually: createdb companyfinder"
    fi
else
    echo -e "${YELLOW}⏭️  Skipped database creation${NC}"
fi
echo ""

# Step 8: Run migrations
echo -e "${BLUE}8️⃣  Running database migrations...${NC}"
read -p "   Run Alembic migrations? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Generate initial migration
    echo "   Generating initial migration..."
    alembic revision --autogenerate -m "Initial schema - Phase 1 and 2"

    # Apply migrations
    echo "   Applying migrations..."
    alembic upgrade head

    echo -e "${GREEN}✅ Migrations complete${NC}"
else
    echo -e "${YELLOW}⏭️  Skipped migrations${NC}"
    echo "   Run manually: alembic revision --autogenerate -m 'Initial schema' && alembic upgrade head"
fi
echo ""

# Summary
echo -e "${GREEN}🎉 Setup Complete!${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo ""
echo "1. ${YELLOW}Configure .env file:${NC}"
echo "   nano .env"
echo ""
echo "   Required settings:"
echo "   - DATABASE_URL"
echo "   - SENDGRID_API_KEY (or leave blank for console logging)"
echo "   - AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_BUCKET_NAME)"
echo ""
echo "2. ${YELLOW}Start development server:${NC}"
echo "   source venv/bin/activate"
echo "   uvicorn app.main:app --reload"
echo ""
echo "3. ${YELLOW}Access API documentation:${NC}"
echo "   http://localhost:8000/docs"
echo ""
echo "4. ${YELLOW}Run tests:${NC}"
echo "   bash scripts/test_auth.sh"
echo ""
echo -e "${GREEN}Happy coding! 🚀${NC}"
