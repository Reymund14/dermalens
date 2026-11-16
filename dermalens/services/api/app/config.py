from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///./dermalens-dev.db"))
    # Dev defaults only. Production must set real secrets (see README).
    jwt_secret: str = field(default_factory=lambda: _env("JWT_SECRET", "dev-only-change-me-dev-only-change-me"))
    data_key: str = field(default_factory=lambda: _env("DATA_KEY", "AUlI14Gsve1MbMj__iKvEHTJjVfIpWKZgqWV7PFn3FY="))
    storage_dir: Path = field(default_factory=lambda: Path(_env("STORAGE_DIR", "./storage")))
    inference_url: str = field(default_factory=lambda: _env("INFERENCE_URL", ""))  # empty = in-process
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
    cors_origins: list[str] = field(default_factory=lambda: _env("CORS_ORIGINS", "*").split(","))


settings = Settings()
