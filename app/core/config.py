from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    app_name: str = "EnterpriseFlow API"
    app_version: str = "0.1.0"

    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_db: str = "enterpriseflow"
    postgres_test_db: str = "enterpriseflow_test"
    postgres_user: str = "enterpriseflow"
    postgres_password: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    outbox_batch_size: int = Field(default=10, ge=1, le=1000)
    outbox_poll_interval: float = Field(default=5.0, gt=0)
    outbox_max_attempts: int = Field(default=5, ge=1, le=100)
    outbox_retry_delay: float = Field(default=60.0, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def test_database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_test_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
