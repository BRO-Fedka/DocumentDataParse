from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_api_key: str = Field(..., alias="APP_API_KEY")
    yandex_api_key: str = Field(..., alias="YANDEX_API_KEY")
    yandex_folder_id: str = Field(..., alias="YANDEX_FOLDER_ID")

    # Max input tokens for the whole GPT request (system + user).
    gpt_max_input_tokens: int = Field(32760, alias="GPT_MAX_INPUT_TOKENS")
    # Hard conversion: tokens -> characters.
    chars_per_token: int = Field(2, alias="CHARS_PER_TOKEN")

    # Retry same block on bad JSON / GPT errors (N).
    gpt_block_retries: int = Field(3, alias="GPT_BLOCK_RETRIES")
    # Restart whole file analysis (M).
    gpt_analysis_retries: int = Field(2, alias="GPT_ANALYSIS_RETRIES")

    max_upload_bytes: int = Field(20 * 1024 * 1024, alias="MAX_UPLOAD_BYTES")
    max_pages: int = Field(100, alias="MAX_PAGES")

    pdf_min_chars_per_page: int = Field(50, alias="PDF_MIN_CHARS_PER_PAGE")
    pdf_scan_image_page_ratio: float = Field(0.5, alias="PDF_SCAN_IMAGE_PAGE_RATIO")
    pdf_force_vision: bool = Field(False, alias="PDF_FORCE_VISION")
    pdf_force_text: bool = Field(False, alias="PDF_FORCE_TEXT")

    yandex_gpt_model: str = Field("yandexgpt-5.1/latest", alias="YANDEX_GPT_MODEL")
    yandex_gpt_temperature: float = Field(0.1, alias="YANDEX_GPT_TEMPERATURE")
    yandex_gpt_max_tokens: int = Field(2000, alias="YANDEX_GPT_MAX_TOKENS")

    log_dir: str = Field("logs", alias="LOG_DIR")
    log_retention: str = Field("30 days", alias="LOG_RETENTION")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    temp_dir: str = Field("tmp_uploads", alias="TEMP_DIR")

    @property
    def max_input_chars(self):
        # type: () -> int
        return int(self.gpt_max_input_tokens) * int(self.chars_per_token)

    @property
    def log_dir_path(self):
        # type: () -> Path
        path = Path(self.log_dir)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path

    @property
    def temp_dir_path(self):
        # type: () -> Path
        path = Path(self.temp_dir)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path


@lru_cache()
def get_settings():
    # type: () -> Settings
    return Settings()
