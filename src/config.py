from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    stardb_url: str = "postgresql+asyncpg://wakr:wakr@localhost:5432/wakr"
    debug: bool = False
    token_issuer: str = ""
    token_audience: str = ""
    jwt_public_key: str = ""
    analytics_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent / ".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
