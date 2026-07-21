import json
import re
from typing import Any, Dict

import requests
from loguru import logger

from app.config import Settings
from app.services.schema_state import state_to_json


class YandexGptError(RuntimeError):
    pass


SYSTEM_PROMPT = (
    "Ты — ассистент, который извлекает структурированные данные из документов. "
    "Отвечай только JSON-объектом той же структуры, что в текущем состоянии. "
    "Поля со значением \"???\" заполняй, если данные есть во фрагменте. "
    "Если данных нет — оставляй \"???\". "
    "Уже заполненные поля обычно сохраняй. "
    "Перезаписывать уже найденное значение разрешено только очень осторожно: "
    "когда во фрагменте есть явно более точные или исправляющие данные "
    "(опечатка, неполная запись, противоречие с более надёжным местом документа). "
    "Не меняй значения наугад и не подставляй догадки."
)


def build_user_message(prompt_template, state_json, block_text):
    # type: (str, str, str) -> str
    """Client prompt + current JSON state + document block."""
    base = prompt_template
    if "{raw_text}" in base:
        base = base.replace("{raw_text}", block_text)
        return (
            "{}\n\nТекущее состояние JSON:\n{}\n".format(base.rstrip(), state_json)
        )
    return (
        "{}\n\nТекущее состояние JSON:\n{}\n\n"
        "Фрагмент документа:\n---\n{}\n---".format(
            prompt_template.rstrip(), state_json, block_text
        )
    )


def _extract_json_object(gpt_text):
    # type: (str) -> Dict[str, Any]
    text = gpt_text.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group(0))

    if not isinstance(data, dict):
        raise ValueError("GPT response JSON must be an object")
    return data


def extract_fields_with_gpt(block_text, settings, prompt_template, state):
    # type: (str, Settings, str, Dict[str, Any]) -> Dict[str, Any]
    state_json = state_to_json(state)
    user_text = build_user_message(prompt_template, state_json, block_text)
    model_uri = "gpt://{}/{}".format(settings.yandex_folder_id, settings.yandex_gpt_model)

    total_chars = len(SYSTEM_PROMPT) + len(user_text)
    if total_chars > settings.max_input_chars:
        raise YandexGptError(
            "Request exceeds input budget: {} > {} chars".format(
                total_chars, settings.max_input_chars
            )
        )

    logger.info(
        "YandexGPT request modelUri={} input_chars={}", model_uri, total_chars
    )

    response = requests.post(
        "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
        headers={
            "Authorization": "Api-Key {}".format(settings.yandex_api_key),
            "Content-Type": "application/json",
        },
        json={
            "modelUri": model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": settings.yandex_gpt_temperature,
                "maxTokens": str(settings.yandex_gpt_max_tokens),
            },
            "messages": [
                {"role": "system", "text": SYSTEM_PROMPT},
                {"role": "user", "text": user_text},
            ],
        },
        timeout=180,
    )
    if response.status_code != 200:
        raise YandexGptError(
            "YandexGPT error: {} {}".format(response.status_code, response.text)
        )

    result = response.json()
    try:
        gpt_text = result["result"]["alternatives"][0]["message"]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise YandexGptError("Unexpected YandexGPT response: {}".format(result)) from exc

    logger.info("YandexGPT raw response:\n{}", gpt_text)
    return _extract_json_object(gpt_text)
