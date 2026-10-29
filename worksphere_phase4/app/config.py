"""Secure environment configuration. All secrets come from the environment / .env."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    secret_key: str
    database_url: str
    access_token_expire_minutes: int
    cors_origins: tuple
    email_enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    smtp_from: str


def load_settings() -> Settings:
    key = os.getenv("SECRET_KEY", "")
    if len(key) < 32:
        raise RuntimeError(
            "SECRET_KEY is missing or too short (need 32+ characters). Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))" and put it in .env'
        )
    origins = tuple(o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip())
    return Settings(
        secret_key=key,
        database_url=os.getenv("DATABASE_URL", "sqlite:///./worksphere.db"),
        access_token_expire_minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")),
        cors_origins=origins,
        email_enabled=_bool("EMAIL_ENABLED", False),
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_username=os.getenv("SMTP_USERNAME", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_use_tls=_bool("SMTP_USE_TLS", True),
        smtp_from=os.getenv("SMTP_FROM", "hr@example.com"),
    )


settings = load_settings()
