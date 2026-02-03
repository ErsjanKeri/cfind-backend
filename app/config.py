"""Application configuration using Pydantic Settings."""

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Configuration can be provided via:
    - Environment variables
    - .env file
    - Direct assignment (for testing)
    """

    # ========================================================================
    # APP CONFIGURATION
    # ========================================================================
    APP_NAME: str = "CompanyFinder Albania API"
    APP_URL: str = "http://localhost:3000"
    API_PREFIX: str = "/api"
    ENVIRONMENT: str = "development"  # development | staging | production

    # ========================================================================
    # DATABASE
    # ========================================================================
    DATABASE_URL: str

    # ========================================================================
    # JWT AUTHENTICATION
    # ========================================================================
    JWT_PRIVATE_KEY_PATH: str = "keys/jwt_private.pem"
    JWT_PUBLIC_KEY_PATH: str = "keys/jwt_public.pem"
    JWT_ALGORITHM: str = "RS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_TOKEN_EXPIRE_DAYS_REMEMBER: int = 30

    # ========================================================================
    # CORS (Cross-Origin Resource Sharing)
    # ========================================================================
    CORS_ORIGINS: str = "http://localhost:3000,https://www.cfind.ai,https://cfind.ai"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    # ========================================================================
    # COOKIE CONFIGURATION
    # ========================================================================
    # For cross-subdomain cookies (e.g., www.cfind.ai + api.cfind.ai)
    # Set to ".cfind.ai" in production, None for localhost
    COOKIE_DOMAIN: Optional[str] = None

    @property
    def cookie_domain(self) -> Optional[str]:
        """Get cookie domain for cross-subdomain support."""
        if self.ENVIRONMENT == "production" and self.COOKIE_DOMAIN:
            return self.COOKIE_DOMAIN
        return None  # No domain restriction for development

    # ========================================================================
    # EMAIL CONFIGURATION (SMTP - ZeptoMail)
    # ========================================================================
    SMTP_HOST: str = "smtp.zeptomail.eu"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = "emailapikey"
    SMTP_PASSWORD: Optional[str] = None

    # Email sender details
    EMAIL_FROM: str = "noreply@cfind.ai"
    EMAIL_FROM_NAME: str = "CompanyFinder Albania"

    # ========================================================================
    # AWS S3 / DigitalOcean Spaces
    # ========================================================================
    AWS_REGION: str = "eu-central-1"
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_BUCKET_NAME: str
    AWS_ENDPOINT: Optional[str] = None  # For DigitalOcean Spaces

    # ========================================================================
    # CRON JOBS
    # ========================================================================
    CRON_SECRET: Optional[str] = None

    # ========================================================================
    # CURRENCY
    # ========================================================================
    EUR_TO_LEK_RATE: float = 100.0  # Initial rate, updated daily

    # ========================================================================
    # PYDANTIC SETTINGS CONFIG
    # ========================================================================
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Ignore extra fields in .env
    )


# ============================================================================
# GLOBAL SETTINGS INSTANCE
# ============================================================================
settings = Settings()


# ============================================================================
# LOAD JWT KEYS
# ============================================================================
def load_jwt_keys() -> tuple[str, str]:
    """
    Load RS256 JWT private and public keys from files.

    Returns:
        tuple: (private_key, public_key) as strings

    Raises:
        FileNotFoundError: If key files don't exist
        IOError: If key files can't be read
    """
    private_key_path = settings.JWT_PRIVATE_KEY_PATH
    public_key_path = settings.JWT_PUBLIC_KEY_PATH

    # Check if keys exist
    if not os.path.exists(private_key_path):
        raise FileNotFoundError(
            f"JWT private key not found at {private_key_path}. "
            f"Run 'bash scripts/generate_jwt_keys.sh' to generate keys."
        )

    if not os.path.exists(public_key_path):
        raise FileNotFoundError(
            f"JWT public key not found at {public_key_path}. "
            f"Run 'bash scripts/generate_jwt_keys.sh' to generate keys."
        )

    # Read keys
    with open(private_key_path, "r") as f:
        private_key = f.read()

    with open(public_key_path, "r") as f:
        public_key = f.read()

    return private_key, public_key


# Load JWT keys on module import
try:
    JWT_PRIVATE_KEY, JWT_PUBLIC_KEY = load_jwt_keys()
except FileNotFoundError as e:
    # Allow import even if keys don't exist (for migrations, scripts, etc.)
    print(f"Warning: {e}")
    JWT_PRIVATE_KEY = None
    JWT_PUBLIC_KEY = None
