"""Platform configuration.

Defaults are chosen so the platform runs with zero external services.
Set DECARBX_DATABASE_URL to a PostgreSQL DSN for a production deployment.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


class Settings:
    app_name: str = "Nexgile-DecarbX Environmental Intelligence Platform"
    version: str = "1.0.0"
    database_url: str = os.getenv(
        "DECARBX_DATABASE_URL", f"sqlite:///{(DATA_DIR / 'decarbx.db').as_posix()}"
    )
    # FR-3.A.4 / FR-7.3 - the GWP set is part of methodology versioning.
    default_gwp_set: str = "AR6"
    default_method_version: str = "GHGP-2024.1"
    # FR-3.C.1 - 25+ languages for supplier engagement.
    supported_languages: list[str] = [
        "en", "de", "fr", "es", "pt", "it", "nl", "pl", "cs", "sv", "da", "fi",
        "no", "tr", "ru", "uk", "ar", "he", "hi", "bn", "ta", "zh-CN", "zh-TW",
        "ja", "ko", "th", "vi", "id", "ms",
    ]
    upload_dir: Path = DATA_DIR / "uploads"


settings = Settings()
settings.upload_dir.mkdir(exist_ok=True)
