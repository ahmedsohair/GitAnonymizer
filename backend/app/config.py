from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./app.db"
    redis_url: str = "redis://localhost:6379/0"
    mirror_storage_root: str = "./storage/mirrors"
    temp_root: str = "./storage/tmp"
    default_url_ttl_days: int = 90
    api_prefix: str = ""
    max_file_size_bytes: int = 2_000_000


settings = Settings()

