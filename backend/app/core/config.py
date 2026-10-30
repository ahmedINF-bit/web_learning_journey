from pydantic_settings import BaseSettings
from typing import Literal, Optional

class Settings(BaseSettings):
    APP_NAME: str = "Talaba AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/talaba_ai"
    DATABASE_URL_SYNC: str = "postgresql://postgres:postgres@localhost:5432/talaba_ai"

    SECRET_KEY: str = "your-secret-key-change-in-production-please"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"

    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB

    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]
    FRONTEND_URL: str = "http://localhost:5173"
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    RATE_LIMIT_STORAGE_URI: str = "memory://"
    PASSWORD_RESET_RATE_LIMIT: str = "3/minute"

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
    }

    # Chargily Pay
    CHARGILY_API_KEY: str = ""
    CHARGILY_MODE: Literal["test", "live"] = "test"
    CHARGILY_WEBHOOK_ENDPOINT: Optional[str] = None

    # Billing
    BILLING_ENABLED: bool = False

    # Prices in Algerian dinars (DZD)
    BILLING_PRO_PRICE_DZD: int = 0
    BILLING_ENTERPRISE_PRICE_DZD: int = 0

    # Subscription duration
    BILLING_SUBSCRIPTION_DAYS: int = 30

settings = Settings()
