import os
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
CHROMA_DIR = BASE_DIR / "chroma_db"

UPLOAD_DIR.mkdir(exist_ok=True)
CHROMA_DIR.mkdir(exist_ok=True)

_env_file = BASE_DIR.parent / ".env"
if _env_file.exists():
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


class Settings:
    GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
    OPENAI_API_KEY: Optional[str] = os.environ.get("OPENAI_API_KEY")
    STT_MODEL: str = os.environ.get("STT_MODEL", "whisper-large-v3")
    LLM_MODEL: str = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")
    DATABASE_URL: str = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR}/videonotes.db")
    MAX_FILE_SIZE_MB: int = int(os.environ.get("MAX_FILE_SIZE_MB", "200"))
    CHUNK_SIZE_TOKENS: int = int(os.environ.get("CHUNK_SIZE_TOKENS", "800"))
    CHUNK_OVERLAP_TOKENS: int = int(os.environ.get("CHUNK_OVERLAP_TOKENS", "150"))
    EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    TOP_K_RESULTS: int = int(os.environ.get("TOP_K_RESULTS", "5"))
    APP_NAME: str = "VideoNotes AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"
    CORS_ORIGINS: list = ["*"]
    UPLOAD_DIR: Path = UPLOAD_DIR
    CHROMA_DIR: Path = CHROMA_DIR


settings = Settings()