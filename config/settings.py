"""
config/settings.py
------------------
Centralised settings loaded from .env via pydantic-settings.
Import `settings` anywhere in the project — no os.getenv() scattered around.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_max_tokens: int = 4096
    gemini_temperature: float = 0.1

    # MCP server
    mcp_server_name: str = "gorules-compiler"
    mcp_server_host: str = "0.0.0.0"
    mcp_server_port: int = 8000
    mcp_transport: str = "sse"

    # Data paths
    tables_dir: str = "data/tables"
    rules_file: str = "data/rules/rules.csv"

    # Logging
    log_level: str = "INFO"

    # Derived helpers (not env vars)
    @property
    def tables_path(self) -> Path:
        return Path(self.tables_dir)

    @property
    def rules_path(self) -> Path:
        return Path(self.rules_file)


settings = Settings()