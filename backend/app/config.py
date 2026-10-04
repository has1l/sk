from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "puzzle"
    bi_reader_password: str = "bi_reader"

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    row_limit: int = 50_000

    @property
    def bi_reader_dsn(self) -> str:
        return (
            f"postgresql://bi_reader:{self.bi_reader_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def has_openai(self) -> bool:
        return self.openai_api_key.startswith("sk-") and len(self.openai_api_key) > 20


settings = Settings()
