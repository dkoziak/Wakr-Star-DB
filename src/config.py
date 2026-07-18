from pathlib import Path
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    stardb_url: Optional[str] = None
    stardb_host: Optional[str] = None
    stardb_port: Optional[str] = None
    stardb_db: Optional[str] = None
    stardb_user: Optional[str] = None
    stardb_password: Optional[str] = None

    debug: bool = False
    token_issuer: str = ""
    token_audience: str = ""
    jwt_public_key: str = ""
    analytics_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
    )

    @model_validator(mode="after")
    def assemble_db_url(self) -> "Settings":
        if self.stardb_url:
            return self

        host = self.stardb_host or "localhost"
        port = self.stardb_port or "5432"
        db = self.stardb_db or "wakr"
        user = self.stardb_user or "wakr"
        pwd = self.stardb_password or "wakr"

        self.stardb_url = f"postgresql+asyncpg://{user}:{pwd}@{host}:{port}/{db}"
        return self


settings = Settings()
