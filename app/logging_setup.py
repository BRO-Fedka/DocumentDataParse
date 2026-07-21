import sys

from loguru import logger

from app.config import Settings


def setup_logging(settings):
    # type: (Settings) -> None
    settings.log_dir_path.mkdir(parents=True, exist_ok=True)
    log_file = settings.log_dir_path / "app_{time:YYYY-MM-DD}.log"

    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
            "<level>{message}</level>"
        ),
    )
    logger.add(
        str(log_file),
        level=settings.log_level,
        rotation="00:00",
        retention=settings.log_retention,
        encoding="utf-8",
        enqueue=True,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
    )
