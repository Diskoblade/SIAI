"""Environment-backed settings for the local OpenHands provisioner."""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    provisioner_api_key: str
    public_url: str = "http://localhost:8090"
    database_path: str = "/data/provisioner.db"

    openhands_image: str = "ghcr.io/openhands/agent-canvas:1.8.0"
    docker_network: str = "sih-openhands"
    workspace_memory_limit: str = "4g"
    workspace_cpu_limit: float = 2.0
    workspace_pids_limit: int = 512
    workspace_startup_timeout_seconds: int = 240
    runtime_probe_timeout_seconds: float = 2.0

    launch_ticket_ttl_seconds: int = 60
    browser_session_ttl_seconds: int = 8 * 60 * 60
    session_cookie_name: str = "sih_oh_session"
    proxy_timeout_seconds: float = 600.0

    @field_validator("provisioner_api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 32:
            raise ValueError("PROVISIONER_API_KEY must contain at least 32 characters")
        return value

    @field_validator("public_url")
    @classmethod
    def validate_public_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("PUBLIC_URL must be an absolute HTTP(S) origin")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("PUBLIC_URL must not contain a path, query, or fragment")
        return value

    @property
    def secure_cookie(self) -> bool:
        return self.public_url.startswith("https://")

