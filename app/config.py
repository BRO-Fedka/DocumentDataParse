from functools import lru_cache
from pathlib import Path
from typing import Optional

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

    host: str = Field("0.0.0.0", alias="HOST")
    port: int = Field(8000, alias="PORT")
    debug: bool = Field(False, alias="DEBUG")

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
    pdf_image_page_area_ratio: float = Field(0.35, alias="PDF_IMAGE_PAGE_AREA_RATIO")

    yandex_gpt_model: str = Field("yandexgpt-lite/latest", alias="YANDEX_GPT_MODEL")
    yandex_gpt_temperature: float = Field(0.1, alias="YANDEX_GPT_TEMPERATURE")
    yandex_gpt_max_tokens: int = Field(2000, alias="YANDEX_GPT_MAX_TOKENS")
    # Async completion (cheaper tariff). Sync URL was .../completion.
    yandex_gpt_api_url: str = Field(
        "https://llm.api.cloud.yandex.net/foundationModels/v1/completionAsync",
        alias="YANDEX_GPT_API_URL",
    )
    yandex_operations_api_url: str = Field(
        "https://operation.api.cloud.yandex.net/operations",
        alias="YANDEX_OPERATIONS_API_URL",
    )
    yandex_vision_api_url: str = Field(
        "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText",
        alias="YANDEX_VISION_API_URL",
    )

    gpt_http_timeout_seconds: int = Field(60, alias="GPT_HTTP_TIMEOUT_SECONDS")
    # Total wait for one async completion (submit + polls).
    gpt_async_timeout_seconds: int = Field(300, alias="GPT_ASYNC_TIMEOUT_SECONDS")
    gpt_async_poll_interval_seconds: float = Field(
        1.0, alias="GPT_ASYNC_POLL_INTERVAL_SECONDS"
    )
    vision_http_timeout_seconds: int = Field(120, alias="VISION_HTTP_TIMEOUT_SECONDS")

    # Comma-separated lists
    vision_language_codes: str = Field("ru,en", alias="VISION_LANGUAGE_CODES")
    vision_text_types: str = Field("printed", alias="VISION_TEXT_TYPES")

    system_prompt_file: str = Field(
        str(ROOT_DIR / "system_prompt.txt"), alias="SYSTEM_PROMPT_FILE"
    )

    merge_allow_overwrite: bool = Field(True, alias="MERGE_ALLOW_OVERWRITE")

    log_dir: str = Field("logs", alias="LOG_DIR")
    log_retention: str = Field("30 days", alias="LOG_RETENTION")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    temp_dir: str = Field("tmp_uploads", alias="TEMP_DIR")

    @property
    def max_input_chars(self):
        # type: () -> int
        return int(self.gpt_max_input_tokens) * int(self.chars_per_token)

    @property
    def system_prompt_path(self):
        # type: () -> Path
        path = Path(self.system_prompt_file)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path

    @property
    def vision_language_codes_list(self):
        # type: () -> list
        codes = [
            part.strip()
            for part in self.vision_language_codes.split(",")
            if part.strip()
        ]
        # Empty env (VISION_LANGUAGE_CODES=) must not send [] to Vision API.
        return codes or ["ru", "en"]

    @property
    def vision_text_types_list(self):
        # type: () -> list
        types = [
            part.strip()
            for part in self.vision_text_types.split(",")
            if part.strip()
        ]
        return types or ["printed"]

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


def load_system_prompt(settings=None):
    # type: (Optional[Settings]) -> str
    if settings is None:
        settings = get_settings()
    path = settings.system_prompt_path
    if not path.is_file():
        raise FileNotFoundError("System prompt file not found: {}".format(path))
    return path.read_text(encoding="utf-8").strip()
