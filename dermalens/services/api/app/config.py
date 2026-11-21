from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Set DERMALENS_ENV=production in every real deployment. It turns missing
# secrets into a startup error instead of a generated temporary value.
PRODUCTION = os.getenv("DERMALENS_ENV", "development").strip().lower() in ("production", "prod")


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_bool(name: str, default: str) -> bool:
    return _env(name, default).strip().lower() in ("1", "true", "yes", "on")


def _secret(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"{name} must be set (see dev.sh for local development)")
    return value


def _cors_origins() -> list[str]:
    default = "" if PRODUCTION else "http://localhost:8081,http://localhost:19006"
    origins = [o.strip() for o in _env("CORS_ORIGINS", default).split(",") if o.strip()]
    if PRODUCTION and (not origins or "*" in origins):
        raise RuntimeError("CORS_ORIGINS must list explicit origins when DERMALENS_ENV=production")
    return origins


def _public_base_url() -> str:
    url = _env("PUBLIC_BASE_URL", "")
    if PRODUCTION and not url.startswith("https://"):
        raise RuntimeError("PUBLIC_BASE_URL must be an HTTPS origin when DERMALENS_ENV=production")
    return url


def _public_web_url() -> str:
    url = _env("PUBLIC_WEB_URL", "http://localhost:5173").rstrip("/")
    if PRODUCTION and not url.startswith("https://"):
        raise RuntimeError("PUBLIC_WEB_URL must be an HTTPS origin when DERMALENS_ENV=production")
    return url


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///./dermalens-dev.db"))
    jwt_secret: str = field(default_factory=lambda: _secret("JWT_SECRET"))
    data_key: str = field(default_factory=lambda: _secret("DATA_KEY"))
    storage_dir: Path = field(default_factory=lambda: Path(_env("STORAGE_DIR", "./storage")))
    supabase_url: str = field(default_factory=lambda: _env("SUPABASE_URL", ""))
    supabase_service_key: str = field(default_factory=lambda: _env("SUPABASE_SERVICE_ROLE_KEY", ""))
    supabase_bucket: str = field(default_factory=lambda: _env("SUPABASE_STORAGE_BUCKET", "dermalens"))
    inference_url: str = field(default_factory=lambda: _env("INFERENCE_URL", ""))  # empty = in-process
    # Public origin for share links and QR codes (set behind a reverse proxy).
    public_base_url: str = field(default_factory=_public_base_url)
    # Address of the web app, used in emailed reset and verification links.
    public_web_url: str = field(default_factory=_public_web_url)
    auth_rate_limit_enabled: bool = field(default_factory=lambda: _env_bool("AUTH_RATE_LIMIT_ENABLED", "1"))
    rate_limits: bool = field(default_factory=lambda: _env_bool("RATE_LIMITS", "1"))
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    # Without SMTP_HOST, emails are written to the API log (development/e2e).
    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(_env("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD", ""))
    mail_from: str = field(default_factory=lambda: _env("MAIL_FROM", "DermaLens <no-reply@localhost>"))
    clinic_notify_email: str = field(default_factory=lambda: _env("CLINIC_NOTIFY_EMAIL", ""))
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    upload_url_seconds: int = 300
    share_link_days: int = 30
    retention_months: int = 12
    fda_reverify_days: int = 90
    policy_version: str = "privacy-2026.10"
    questionnaire_version: str = "intake-1.0.0"
    clinic_contact: str = field(default_factory=lambda: _env(
        "CLINIC_CONTACT", "ICONIC Aesthetic Clinic (add address, phone and booking link)"))
    cors_origins: list[str] = field(default_factory=_cors_origins)

    def __post_init__(self) -> None:
        if PRODUCTION and not (self.supabase_url and self.supabase_service_key):
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set when DERMALENS_ENV=production")


settings = Settings()
