import json
import re
import time
from typing import Any, Dict

import requests
from loguru import logger

from app.config import Settings, load_system_prompt
from app.services.schema_state import state_to_json


class YandexGptError(RuntimeError):
    pass


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


def build_gpt_messages(prompt_template, state, block_text, settings):
    # type: (str, dict, str, Settings) -> tuple
    """
    Exact system + user texts that will be sent to YandexGPT.
    Used both for budget measurement and the real async submit.
    """
    system_prompt = load_system_prompt(settings)
    state_json = state_to_json(state, compact=True)
    user_text = build_user_message(prompt_template, state_json, block_text)
    return system_prompt, user_text


def measure_request_chars(prompt_template, state, block_text, settings):
    # type: (str, dict, str, Settings) -> int
    """Full GPT request size (system + user) with the given state."""
    system_prompt, user_text = build_gpt_messages(
        prompt_template, state, block_text, settings
    )
    return len(system_prompt) + len(user_text)


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


def _auth_headers(settings):
    # type: (Settings) -> Dict[str, str]
    return {
        "Authorization": "Api-Key {}".format(settings.yandex_api_key),
        "Content-Type": "application/json",
    }


def _completion_text_from_payload(payload):
    # type: (Dict[str, Any]) -> str
    """Extract assistant text from sync `result` or async operation `response`."""
    try:
        return payload["alternatives"][0]["message"]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise YandexGptError(
            "Unexpected YandexGPT completion payload: {}".format(payload)
        ) from exc


def _submit_async_completion(settings, model_uri, system_prompt, user_text):
    # type: (Settings, str, str, str) -> str
    response = requests.post(
        settings.yandex_gpt_api_url,
        headers=_auth_headers(settings),
        json={
            "modelUri": model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": settings.yandex_gpt_temperature,
                "maxTokens": str(settings.yandex_gpt_max_tokens),
            },
            "messages": [
                {"role": "system", "text": system_prompt},
                {"role": "user", "text": user_text},
            ],
        },
        timeout=settings.gpt_http_timeout_seconds,
    )
    if response.status_code != 200:
        raise YandexGptError(
            "YandexGPT async submit error: {} {}".format(
                response.status_code, response.text
            )
        )

    data = response.json()
    operation_id = data.get("id")
    if not operation_id:
        raise YandexGptError(
            "YandexGPT async submit missing operation id: {}".format(data)
        )
    return operation_id


def _poll_operation(settings, operation_id):
    # type: (Settings, str) -> Dict[str, Any]
    """Poll until operation.done or GPT_ASYNC_TIMEOUT_SECONDS."""
    url = "{}/{}".format(settings.yandex_operations_api_url.rstrip("/"), operation_id)
    deadline = time.monotonic() + float(settings.gpt_async_timeout_seconds)
    last = None  # type: Dict[str, Any]

    while time.monotonic() < deadline:
        response = requests.get(
            url,
            headers=_auth_headers(settings),
            timeout=settings.gpt_http_timeout_seconds,
        )
        if response.status_code != 200:
            raise YandexGptError(
                "YandexGPT operation poll error: {} {}".format(
                    response.status_code, response.text
                )
            )
        last = response.json()
        if last.get("done"):
            if last.get("error"):
                raise YandexGptError(
                    "YandexGPT async operation failed: {}".format(last["error"])
                )
            return last
        time.sleep(float(settings.gpt_async_poll_interval_seconds))

    raise YandexGptError(
        "YandexGPT async timeout after {}s (operation_id={}, last={})".format(
            settings.gpt_async_timeout_seconds, operation_id, last
        )
    )


def extract_fields_with_gpt(block_text, settings, prompt_template, state):
    # type: (str, Settings, str, Dict[str, Any]) -> Dict[str, Any]
    system_prompt, user_text = build_gpt_messages(
        prompt_template, state, block_text, settings
    )
    model_uri = "gpt://{}/{}".format(settings.yandex_folder_id, settings.yandex_gpt_model)

    total_chars = len(system_prompt) + len(user_text)
    if total_chars > settings.max_input_chars:
        raise YandexGptError(
            "Request exceeds input budget: {} > {} chars".format(
                total_chars, settings.max_input_chars
            )
        )

    logger.info(
        "YandexGPT async request modelUri={} input_chars={} "
        "system_chars={} user_chars={} block_chars={}",
        model_uri,
        total_chars,
        len(system_prompt),
        len(user_text),
        len(block_text),
    )
    logger.info(
        "YandexGPT FINAL system prompt ({} chars):\n{}",
        len(system_prompt),
        system_prompt,
    )
    logger.info(
        "YandexGPT FINAL user prompt ({} chars):\n{}",
        len(user_text),
        user_text,
    )

    operation_id = _submit_async_completion(
        settings, model_uri, system_prompt, user_text
    )
    logger.info("YandexGPT operation_id={}", operation_id)

    operation = _poll_operation(settings, operation_id)
    # Async Operation puts completion under `response` (sync uses `result`).
    completion = operation.get("response")
    if not isinstance(completion, dict):
        raise YandexGptError(
            "Unexpected YandexGPT async operation body: {}".format(operation)
        )

    gpt_text = _completion_text_from_payload(completion)
    logger.info("YandexGPT raw response:\n{}", gpt_text)
    return _extract_json_object(gpt_text)
