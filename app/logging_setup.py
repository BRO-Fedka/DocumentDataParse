import sys

from loguru import logger

from app.config import Settings


def setup_logging(settings):
    # type: (Settings) -> None
    """Configure console + rotating file sinks (with exception tracebacks)."""
    settings.log_dir_path.mkdir(parents=True, exist_ok=True)
    log_dir = settings.log_dir_path.resolve()
    # Concrete daily file (also keep loguru rotation pattern for midnight).
    log_file = log_dir / "app_{time:YYYY-MM-DD}.log"
    error_file = log_dir / "app_errors_{time:YYYY-MM-DD}.log"

    logger.remove()

    # Console
    logger.add(
        sys.stderr,
        level=settings.log_level,
        backtrace=True,
        diagnose=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
            "<level>{message}</level>\n{exception}"
        ),
    )

    # All levels -> daily file. enqueue=False: more reliable on Windows/Flask threads.
    logger.add(
        str(log_file),
        level=settings.log_level,
        rotation="00:00",
        retention=settings.log_retention,
        encoding="utf-8",
        enqueue=False,
        backtrace=True,
        diagnose=True,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}\n{exception}"
        ),
    )

    # ERROR+ only -> separate file so failures are easy to find.
    logger.add(
        str(error_file),
        level="ERROR",
        rotation="00:00",
        retention=settings.log_retention,
        encoding="utf-8",
        enqueue=False,
        backtrace=True,
        diagnose=True,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}\n{exception}"
        ),
    )

    logger.info("Logging to directory={}", log_dir)
    logger.info("Log files pattern: {} and {}", log_file.name, error_file.name)
