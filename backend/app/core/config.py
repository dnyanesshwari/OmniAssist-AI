from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+psycopg://omni:change_me@localhost:5432/omniassist"
    gemini_api_key: str = ""
    jwt_secret: str = "change_me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12

    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768
    llm_model: str = "gemini-2.5-flash"

    docs_dir: str = "../data/documents"
    rag_top_k: int = 5
    rag_min_similarity: float = 0.55

    # Agent / voice
    max_failures: int = 3
    allow_failure_injection: bool = False  # demo only: lets a request simulate a provider outage
    voice_idle_seconds: int = 20
    server_tts: bool = False  # default: browser speechSynthesis does TTS
    asr_model: str = "gemini-2.5-flash"
    tts_model: str = "gemini-2.5-flash-preview-tts"
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)

    # Business rules (enforced in code, mirrored in data/documents)
    hold_minutes: int = 10
    min_lead_hours: int = 2
    work_start_hour: int = 8
    work_end_hour: int = 20
    supported_cities: tuple[str, ...] = ("Delhi", "Mumbai", "Pune", "Bengaluru", "Hyderabad")


@lru_cache
def get_settings() -> Settings:
    return Settings()
