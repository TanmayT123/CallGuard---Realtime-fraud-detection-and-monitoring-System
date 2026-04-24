"""Application settings and configuration."""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings

# Get absolute path to project root (parent of backend directory)
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "fraud_detection.db"


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Application
    app_name: str = "Fraud Detection System"
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "True").lower() == "true"
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Database - Use absolute path to ensure single database
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{DB_PATH}"
    )
    
    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Twilio
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_phone_number: str = os.getenv("TWILIO_PHONE_NUMBER", "")
    twilio_webhook_url: str = os.getenv("TWILIO_WEBHOOK_URL", "https://your-ngrok-url.ngrok.io")
    ngrok_url: str = os.getenv("NGROK_URL", "wss://your-ngrok-url.ngrok-free.dev")

    # Ollama / LLM
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    llm_timeout: float = 2.0  # seconds

    # Audio
    whisper_model_size: str = "base"  # tiny, base, small, medium
    audio_sample_rate: int = 16000
    audio_chunk_duration_ms: int = 20
    audio_buffer_duration_seconds: int = 2

    # Detection
    tier1_high_threshold: int = 75  # Lowered from 85 for better detection
    tier1_medium_threshold: int = 50
    
    # ChromaDB
    chromadb_host: str = os.getenv("CHROMADB_HOST", "localhost")
    chromadb_port: int = int(os.getenv("CHROMADB_PORT", "8000"))

    # Frontend
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    cors_origins: list = ["*"]  # Change to specific origins in production

    # Monitoring
    sentry_dsn: Optional[str] = os.getenv("SENTRY_DSN")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
