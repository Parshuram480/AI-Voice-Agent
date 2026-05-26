"""
Configuration module — loads all settings directly using python-dotenv and os.getenv.

Usage:
    from app.config import settings
    print(settings.GROQ_API_KEY)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Ensure we find the .env file in the root directory regardless of where we run from
ROOT_DIR = Path(__file__).parent.parent
ENV_PATH = ROOT_DIR / ".env"

# Explicitly load .env into os.environ
load_dotenv(dotenv_path=ENV_PATH)


class Settings:
    """Application settings loaded directly from environment variables / .env file."""

    # --- Twilio ---
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

    # --- Groq AI ---
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

    # --- PostgreSQL ---
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "voice_agent")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # --- Server ---
    SERVER_HOST = os.getenv("SERVER_HOST", "http://localhost:8000")
    SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

    # --- Streaming Pipeline Tuning ---
    STT_EARLY_CHUNK_SECONDS = float(os.getenv("STT_EARLY_CHUNK_SECONDS", "1.0"))
    SILENCE_THRESHOLD = int(os.getenv("SILENCE_THRESHOLD", "500"))
    SILENCE_DURATION_MS = int(os.getenv("SILENCE_DURATION_MS", "1500"))
    TTS_CACHE_SIZE = int(os.getenv("TTS_CACHE_SIZE", "100"))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "96"))
    TWILIO_STREAM_AUDIO_OUT = os.getenv("TWILIO_STREAM_AUDIO_OUT", "true").lower() in ("1", "true", "yes", "on")

    @property
    def database_url(self) -> str:
        """PostgreSQL connection DSN for asyncpg."""
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

# Singleton instance — import this everywhere


settings = Settings()
