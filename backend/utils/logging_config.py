"""Logging configuration."""
import sys
from pathlib import Path
import logging
import logging.handlers
import os

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.config import settings

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)


def setup_logging():
    """Setup application logging."""
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(settings.log_level)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler
    file_handler = logging.handlers.RotatingFileHandler(
        'logs/fraud_detection.log',
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(settings.log_level)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(pathname)s:%(lineno)d] - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    return root_logger


# Setup logging on import
logger = setup_logging()
