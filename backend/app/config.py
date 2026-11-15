from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "puzzle"
    bi_reader_password: str = "bi_reader"
    app_password: str = "app"

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    row_limit: int = 50_000
    # Детальная таблица живёт в памяти сессии и в браузер не уезжает,
    # поэтому её потолок выше: вся плоская таблица — 122 719 строк.
    detail_row_limit: int = 200_000
    session_ttl_minutes: int = 180
    max_sessions: int = 64
    # Каждая реплика — платный вызов модели. Потолок не даёт скрипту или
    # залипшей клавише выжечь бюджет OpenAI.
    ask_per_minute: int = 30

    # Публичный прототип: пароль на весь сайт и собранный веб с того же адреса.
    # Пустые — локальный режим: пароля нет, веб отдаёт Vite.
    site_password: str = ""
    web_dist: str = ""

    @property
    def bi_reader_dsn(self) -> str:
        return (
            f"postgresql://bi_reader:{self.bi_reader_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def app_dsn(self) -> str:
        return (
            f"postgresql://app:{self.app_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def has_openai(self) -> bool:
        return self.openai_api_key.startswith("sk-") and len(self.openai_api_key) > 20


settings = Settings()
