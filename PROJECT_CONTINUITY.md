# DocumentDataParse — continuity handoff

Критичные решения для продолжения работы после смены чата/контекста.
Обновлено: 2026-08-23. Remote: `https://github.com/BRO-Fedka/DocumentDataParse.git` (`main`).

## Цель продукта

Flask API: загрузка PDF/DOCX → извлечение текста → YandexGPT (клиентский prompt + JSON-скелет) → JSON полей. Клиент: Delphi. Деплой: VPS (сейчас Windows, `python main.py` / `app.main`), целевой Ubuntu. Файлы и сырой текст долго не хранить.

## Архитектура пайплайна

1. Атомы: PDF = страницы; DOCX = параграфы/таблицы по порядку.
2. Динамическая нарезка блоков: `take_next_block` с учётом **текущего** JSON state (`measure_request_chars`).
3. Последовательные вызовы GPT; merge в state; ретраи блока (N) и анализа (M).
4. Ранний выход, если `is_state_complete(state)`.

Ключевые файлы: `app/services/pipeline.py`, `blocking.py`, `yandex_gpt.py`, `schema_state.py`, `pdf_extract.py`, `docx_extract.py`, `vision.py`.

## Yandex / стоимость

- Модель: **`yandexgpt-lite/latest`** (не Pro 5.1).
- Режим: **async** — `completionAsync` + poll `operation.api.cloud.yandex.net/operations/{id}`.
- Sync был дороже ~×2; Pro дороже Lite ~×3–4.
- Async иногда тормозит (минуты на блок) или висит до `GPT_ASYNC_TIMEOUT_SECONDS` (300).

## Merge / качество Lite

Проблема: со 2–3 блока Lite портит хорошие поля (`Заказчик`, `Объект`, укороченный `work_types`).

Сделано:
- Чёрный список плейсхолдеров в `schema_state.py`.
- При `MERGE_ALLOW_OVERWRITE=false`: **skip** конфликта (не raise), лог `Skip overwrite…`.
- Падение блока (content-filter / таймаут): **skip блока**, не валить весь документ.
- `system_prompt.txt`: запрет заглушек и сокращений.

## Логи

- Каталог: `DocumentDataParse/logs/` (от корня репо, не CWD).
- `app_YYYY-MM-DD.log` — всё.
- `app_errors_YYYY-MM-DD.log` — только ERROR+ с traceback.
- `enqueue=False`, явный `{exception}` в формате.
- При старте: `Logging to directory=...`

## Env (важное)

Секреты только в `.env` (gitignored). Шаблон: `.env.example`.

Обязательно на сервере после Lite/async:
```
YANDEX_GPT_MODEL=yandexgpt-lite/latest
YANDEX_GPT_API_URL=https://llm.api.cloud.yandex.net/foundationModels/v1/completionAsync
YANDEX_OPERATIONS_API_URL=https://operation.api.cloud.yandex.net/operations
GPT_HTTP_TIMEOUT_SECONDS=60
GPT_ASYNC_TIMEOUT_SECONDS=300
GPT_ASYNC_POLL_INTERVAL_SECONDS=1
```

Бюджет контекста:
```
GPT_MAX_INPUT_TOKENS=32760
CHARS_PER_TOKEN=2
```
Для русского договора ~2 символа/токен; при отказах Яндекса по лимиту — `CHARS_PER_TOKEN=1`.

Опционально строже: `MERGE_ALLOW_OVERWRITE=false`.

## Известные грабли

1. Имя файла Delphi MIME (`=?KOI8-R?B?...=`) — косметика.
2. Content-filter Yandex на отдельных кусках DOCX: `code 3` / «не могу обсуждать» — блок скипается.
3. Dev-сервер Flask на публичном IP — сканеры бьют `/`, `/.env` (404 ок).
4. Не коммитить `.env` / API keys.

## Недавние коммиты (ориентир)

- `177a2a5` — надёжные error-логи Loguru
- `8844213` — soft-skip overwrite + skip failed blocks
- `296cbdb` — placeholders + early exit
- `12816a6` — Lite + async
- `8f58a1f` — packing по текущему state (budget overrun)

## Деплой на VPS

```
git pull
# сверить .env с .env.example (Lite/async ключи)
# перезапуск python main.py / сервиса
```

После правок `system_prompt.txt` подтягивается с git; путь: `SYSTEM_PROMPT_FILE`.
