from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    PROJECT_NAME: str = "Synora - Knowledge Continuity & Project Protection Platform"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Database configuration
    # In production, set to Supabase PostgreSQL:
    # postgresql+psycopg2://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres
    DATABASE_URL: str = "sqlite:///./synora.db"
    
    # Document storage configuration
    STORAGE_PROVIDER: str = "supabase"  # "supabase" or "local"
    SUPABASE_URL: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_STORAGE_BUCKET: str = "synora-documents"
    SUPABASE_SIGNED_URL_EXPIRES_SECONDS: int = 3600
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB limit
    
    # Security & Authentication
    JWT_SECRET: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    # Explicit values override the environment-based prototype default.
    DEMO_LOGIN_ENABLED: Optional[bool] = None
    # Demo accounts are seeded only when explicitly enabled in development/test.
    DEMO_SEED_ENABLED: bool = False

    # Provider-independent AI configuration
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"
    EMBEDDING_PROVIDER: str = "local"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    model_config = SettingsConfigDict(
        env_file=(str(ENV_FILE_PATH), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    @model_validator(mode="after")
    def validate_auth_configuration(self):
        environment = self.ENVIRONMENT.strip().lower()
        if self.DEMO_LOGIN_ENABLED is None:
            self.DEMO_LOGIN_ENABLED = environment in {"development", "test", "prototype"}
        if environment == "production" and self.DEMO_LOGIN_ENABLED:
            raise ValueError("DEMO_LOGIN_ENABLED must be false in production.")
        if self.DEMO_SEED_ENABLED and environment not in {"development", "test"}:
            raise ValueError("DEMO_SEED_ENABLED is allowed only in development or test environments.")

        # A missing or weak secret must never silently fall back to a known key.
        secret = self.JWT_SECRET
        insecure = (
            not secret
            or len(secret.strip()) < 32
            or any(marker in secret.lower() for marker in ("changeme", "change-me", "placeholder", "replace-with", "your-secret", "test-only"))
        )
        if environment == "production" and insecure:
            raise ValueError("JWT_SECRET must be configured with at least 32 characters in production.")
        if secret and insecure:
            raise ValueError("JWT_SECRET must contain at least 32 characters.")
        return self


settings = Settings()
