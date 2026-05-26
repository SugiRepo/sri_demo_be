import logging
import os
import sys
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
APP_LOGGER_NAME = "app"


def _log_level() -> int:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def _build_file_handler(log_dir: Path) -> logging.Handler:
    log_file = log_dir / "app.log"
    rotation = os.getenv("LOG_ROTATION", "daily").lower()

    if rotation == "size":
        max_bytes = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
        backup_count = int(os.getenv("LOG_BACKUP_COUNT", "10"))
        handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
    else:
        backup_count = int(os.getenv("LOG_BACKUP_COUNT", "30"))
        handler = TimedRotatingFileHandler(
            log_file,
            when="midnight",
            interval=1,
            backupCount=backup_count,
            encoding="utf-8",
            utc=False,
        )
        handler.suffix = "%Y-%m-%d"

    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    return handler


def setup_logging() -> None:
    """
    Configure the ``app`` logger tree (app.services.pdf_ingest, etc.).
    Call from FastAPI lifespan so it runs inside the uvicorn worker process.
    """
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    level = _log_level()
    formatter = logging.Formatter(LOG_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    file_handler = _build_file_handler(log_dir)

    app_logger = logging.getLogger(APP_LOGGER_NAME)
    app_logger.handlers.clear()
    app_logger.setLevel(level)
    app_logger.propagate = False
    app_logger.addHandler(console)
    app_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries unless debugging.
    logging.getLogger("elastic_transport").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    app_logger.info(
        "Logging ready dir=%s rotation=%s level=%s",
        log_dir.resolve(),
        os.getenv("LOG_ROTATION", "daily"),
        logging.getLevelName(level),
    )
