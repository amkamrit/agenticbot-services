from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    QC_BASE_URL: str
    DATABASE_URL: str
    HF_API_KEY: str
    HF_MODEL: str
    GROQ_API_KEY: str
    GROQ_MODEL: str
    LLM_PROVIDER: str
    LLM_TIMEOUT_SECONDS: int
    LLM_MAX_RETRIES: int
    LLM_MAX_OUTPUT_TOKENS: int
    LLM_TEMPERATURE: float
    EMBEDDING_PROVIDER: str
    OLLAMA: str
    OLLAMA_MODEL: str
    VECTORSTORE_PROVIDER: str
    MILVUS_URL: str
    REDIS_URL: str

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
