
from pathlib import Path
from typing import List, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    PROJECT_NAME: str = "Synora - Knowledge Continuity & Project Protection Platform"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "https://synora-b9co.vercel.app",
    ]

    # Database configuration
    DATABASE_URL: str = "sqlite:///./synora.db"

    # Document storage configuration
    STORAGE_PROVIDER: str = "supabase"
    SUPABASE_URL: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_STORAGE_BUCKET: str = "synora-documents"
    SUPABASE_SIGNED_URL_EXPIRES_SECONDS: int = 3600
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 25 * 1024 * 1024

    # Security and authentication
    JWT_SECRET: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    DEMO_LOGIN_ENABLED: Optional[bool] = None
    DEMO_SEED_ENABLED: bool = False
    DEMO_MANAGER_EMAIL: Optional[str] = None
    DEMO_MANAGER_PASSWORD: Optional[str] = None
    DEMO_EMPLOYEE_EMAIL: Optional[str] = None
    DEMO_EMPLOYEE_PASSWORD: Optional[str] = None

    # AI configuration
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"
    EMBEDDING_PROVIDER: str = "local"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    model_config = SettingsConfigDict(
        env_file=(str(ENV_FILE_PATH), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_auth_configuration(self):
        environment = self.ENVIRONMENT.strip().lower()

        if self.DEMO_LOGIN_ENABLED is None:
            self.DEMO_LOGIN_ENABLED = environment in {
                "development",
                "test",
                "prototype",
            }

        if (
            environment == "production"
            and self.DEMO_LOGIN_ENABLED
            and not self.DEMO_SEED_ENABLED
        ):
            raise ValueError(
                "Production demo login requires DEMO_SEED_ENABLED=true "
                "for the isolated sample workspace."
            )

        if self.DEMO_SEED_ENABLED:
            required_demo_credentials = (
                self.DEMO_MANAGER_EMAIL,
                self.DEMO_MANAGER_PASSWORD,
                self.DEMO_EMPLOYEE_EMAIL,
                self.DEMO_EMPLOYEE_PASSWORD,
            )

            if any(
                not value or not value.strip()
                for value in required_demo_credentials
            ):
                raise ValueError(
                    "DEMO_SEED_ENABLED requires manager and employee "
                    "demo email/password configuration."
                )

            if (
                self.DEMO_MANAGER_EMAIL.strip().lower()
                == self.DEMO_EMPLOYEE_EMAIL.strip().lower()
            ):
                raise ValueError(
                    "Manager and employee demo accounts must use "
                    "different email addresses."
                )

            if (
                len(self.DEMO_MANAGER_PASSWORD) < 12
                or len(self.DEMO_EMPLOYEE_PASSWORD) < 12
            ):
                raise ValueError(
                    "Configured demo passwords must contain at least "
                    "12 characters."
                )

            if environment == "production" and (
                self.DEMO_MANAGER_EMAIL.strip().lower()
                != "manager@demo.synora.app"
                or self.DEMO_EMPLOYEE_EMAIL.strip().lower()
                != "employee@demo.synora.app"
            ):
                raise ValueError(
                    "Production demo accounts must use the configured "
                    "public demo email addresses."
                )

        # A missing or weak secret must never silently fall back.
        secret = self.JWT_SECRET

        insecure = (
            not secret
            or len(secret.strip()) < 32
            or any(
                marker in secret.lower()
                for marker in (
                    "changeme",
                    "change-me",
                    "placeholder",
                    "replace-with",
                    "your-secret",
                    "test-only",
                )
            )
        )

        if environment == "production" and insecure:
            raise ValueError(
                "JWT_SECRET must be configured with at least "
                "32 characters in production."
            )

        if secret and insecure:
            raise ValueError(
                "JWT_SECRET must contain at least 32 characters."
            )

        return self


settings = Settings()
