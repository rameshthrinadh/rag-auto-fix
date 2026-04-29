from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OPENAI_API_KEY: str = "your-api-key"
    FAISS_INDEX_PATH: str = "./data/faiss_index/index.faiss"
    INDEX_METADATA_PATH: str = "./data/faiss_index/metadata.pkl"
    RAW_EMBEDDINGS_PATH: str = "./data/faiss_index/embeddings.npy"
    PRIMARY_LLM_MODEL: str = "gpt-4o-mini"
    FALLBACK_LLM_MODEL: str = "gpt-4o"
    EMBEDDING_MODEL: str = "text-embedding-ada-002"
    MAX_RETRIES: int = 2
    REPO_PATH: str = "/tmp/default_repo"
    REPO_MAP_PATH: str = "./data/faiss_index/repo_map.md"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
