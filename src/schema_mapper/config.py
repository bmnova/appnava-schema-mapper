"""Settings loaded from environment variables.

Why env vars only: the repo is public, so nothing project- or key-specific
may live in code. `.env` is loaded for local convenience and is gitignored.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

SOURCE_TABLE = "firebase-public-project.analytics_153293282.events_*"

# Small, fixed window keeps every query cheap and results reproducible.
PROFILE_START = "20180801"
PROFILE_END = "20180803"
VALIDATION_DAY = "20180801"


@dataclass(frozen=True)
class Settings:
    gcp_project: str
    max_bytes_billed: int
    anthropic_model: str | None


def load_settings() -> Settings:
    """Fail fast on a missing GCP project rather than letting the client guess one."""
    load_dotenv()
    project = os.environ.get("GCP_PROJECT")
    if not project:
        raise RuntimeError("GCP_PROJECT is not set (see .env.example)")
    return Settings(
        gcp_project=project,
        max_bytes_billed=int(os.environ.get("MAX_BYTES_BILLED", "1000000000")),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL"),
    )
