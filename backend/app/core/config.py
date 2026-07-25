"""KESSLER runtime configuration (env-driven, .env supported)."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KESSLER_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "KESSLER"
    version: str = "1.0.0"

    # None -> auto: demo mode iff Space-Track credentials are absent
    demo_mode: bool | None = None
    spacetrack_user: str | None = None
    spacetrack_pass: str | None = None
    anthropic_api_key: str | None = None

    data_dir: Path = BACKEND_DIR / "app" / "data"
    log_dir: Path = BACKEND_DIR / "logs"

    # CON-1: cache-first; GP never refetched inside 1 h, CDM inside 30 min
    gp_ttl_seconds: int = 21600      # 6 h — CelesTrak is IP-rate-limited; be gentle
    cdm_ttl_seconds: int = 14400     # 4 h — public CDMs update a few times/day

    screening_max_window_hours: int = 72
    default_hbr_m: float = 20.0
    pipeline_refresh_seconds: int = 14400   # 4 h — was 30 min (too aggressive)

    @property
    def effective_demo_mode(self) -> bool:
        if self.demo_mode is not None:
            return self.demo_mode
        return not (self.spacetrack_user and self.spacetrack_pass)


settings = Settings()
