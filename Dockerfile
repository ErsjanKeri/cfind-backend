# Dockerfile for CompanyFinder Albania FastAPI Backend

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    openssl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create keys directory
RUN mkdir -p keys

# Generate JWT keys if they don't exist
RUN if [ ! -f keys/jwt_private.pem ]; then \
    openssl genrsa -out keys/jwt_private.pem 4096 && \
    openssl rsa -in keys/jwt_private.pem -pubout -out keys/jwt_public.pem && \
    echo "Generated JWT keys"; \
    fi

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run migrations and start server
# Note: In production, run migrations separately before deployment
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
