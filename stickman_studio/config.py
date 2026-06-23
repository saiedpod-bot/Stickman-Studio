"""
config.py
=========
Central configuration loader. Reads a .env file, validates required
credentials, and initializes the Vertex AI SDK exactly once.

Usage:
    from stickman_studio.config import settings, init_vertex
    init_vertex()                 # idempotent
    print(settings.gcp_project_id)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the current working dir or the project root.
load_dotenv()


class ConfigError(RuntimeError):
    """Raised when a required configuration value is missing/invalid."""


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise ConfigError(
            f"Missing required environment variable '{key}'. "
            f"Copy .env.example to .env and fill it in."
        )
    return val


def _int(key: str, default: int) -> int:
    raw = os.getenv(key, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Auth & project
    credentials_path: str
    gcp_project_id: str
    gcp_location: str
    gcs_staging_bucket: str

    # Model IDs
    gemini_model: str
    imagen_generate_model: str
    imagen_capability_model: str
    veo_model: str

    # Tuning
    scene_count: int
    video_seconds: int
    retry_max_attempts: int
    retry_base_delay: int
    log_level: str

    @staticmethod
    def load() -> "Settings":
        creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        # Make ADC discoverable to the underlying client libraries.
        if creds:
            if not Path(creds).is_file():
                raise ConfigError(
                    f"GOOGLE_APPLICATION_CREDENTIALS points to a missing file: {creds}"
                )
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds

        return Settings(
            credentials_path=creds,
            gcp_project_id=_require("GCP_PROJECT_ID"),
            gcp_location=os.getenv("GCP_LOCATION", "us-central1").strip(),
            gcs_staging_bucket=os.getenv("GCS_STAGING_BUCKET", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip(),
            imagen_generate_model=os.getenv(
                "IMAGEN_GENERATE_MODEL", "imagen-3.0-generate-002"
            ).strip(),
            imagen_capability_model=os.getenv(
                "IMAGEN_CAPABILITY_MODEL", "imagen-3.0-capability-001"
            ).strip(),
            veo_model=os.getenv("VEO_MODEL", "veo-2.0-generate-001").strip(),
            scene_count=_int("SCENE_COUNT", 5),
            video_seconds=_int("VIDEO_SECONDS", 10),
            retry_max_attempts=_int("RETRY_MAX_ATTEMPTS", 6),
            retry_base_delay=_int("RETRY_BASE_DELAY", 4),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()


# Convenience singleton
settings = get_settings()


@lru_cache(maxsize=1)
def init_vertex() -> None:
    """Initialize the Vertex AI SDK once for the whole process."""
    import vertexai

    vertexai.init(
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )
