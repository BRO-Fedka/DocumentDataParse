# DocumentDataParse — выжимка разговоров и состояние проекта

Файл для восстановления контекста после переполнения чата.  
Remote: `https://github.com/BRO-Fedka/DocumentDataParse.git` (`main`).  
Обновлено: 2026-08-23.

---

## О чём проект

Нужен безопасный HTTP API: клиент (Delphi) шлёт PDF/DOCX + prompt со JSON-схемой → сервер извлекает текст → YandexGPT заполняет поля → JSON в ответ. Логи через Loguru; файлы/сырой текст долго не хранить. Деплой: Timeweb VPS.

---

## Хронология решений (что обсуждали)

### 1. Базовый пайплайн
Собрали Flask `POST /parse` (multipart: username, prompt, files; header `X-API-Key`).  
PDF: страницы; скан → Yandex Vision OCR. DOCX: параграфы/таблицы.  
Текст режется на блоки под лимит GPT, state JSON с `???`, последовательные вызовы, merge.  
GUI-клиент и prompt-файлы по типам документов (договор / доп / акт). README с контрактом API и примерами Delphi.

### 2. Баг «Request exceeds input budget»
На DOCX падало: `32983 > 32760 chars` — **наш** лимит до вызова Яндекса.  
Причина: блоки паковали с пустым state (`???`), а в запрос уходил уже заполненный JSON → перерасход.  
**Решение:** размер считать по **текущему** state (`measure_request_chars` + `take_next_block` динамически). Compact JSON. Коммит `8f58a1f`.

### 3. Дорого (~40 ₽/документ)
Промпты короткие (~1 KB) — дублирование prompt не главный виновник. Жрёт **объём текста × число блоков × Pro sync**.  
Обсудили: Lite, async (дешевле ~×2), меньше лишних вызовов.  
Ссылки на тарифы: https://yandex.cloud/ru/docs/ai-studio/pricing  
Async = не Python async, а `completionAsync` + poll операции.

### 4. Переход на Lite + async
Модель `yandexgpt-lite/latest`, URL async + poll operations.  
Для Delphi API тот же долгий `POST /parse` — ждёт сервер.  
Коммит `12816a6`. На сервере вручную править `.env` (не в git).

### 5. Деградация качества с блока 2–3
Логи показали: блок 1 хороший; дальше Lite пишет «Заказчик»/«Объект»/«Договор» и **перетирает** нормальные значения (`MERGE_ALLOW_OVERWRITE=true`).  
Предложили: (1) overwrite=false, (2) чёрный список плейсхолдеров, (3) early exit когда всё заполнено.  
Внедрили **2+3** (`296cbdb`) + правки system_prompt.

### 6. Ломающий overwrite=false
На VPS поставили `MERGE_ALLOW_OVERWRITE=false` → конфликт стал **исключением** → ретраи → fail всего файла.  
Параллельно: content-filter Яндекса на куске DOCX; async timeout по 300с.  
**Фикс:** конфликт = `Skip overwrite` (не raise); упавший блок = skip, документ живёт. `8844213`.  
Важно: фикс долго лежал только локально — сервер без pull снова падал с `Overwrite forbidden`.

### 7. Логи ошибок
Ошибки видны в консоли, в файл Loguru — сомнительно (`enqueue=True` на Windows, нет отдельного ERROR-файла).  
Усилили: `enqueue=False`, явный `{exception}`, `logs/app_errors_*.log`, Flask unhandled → loguru. `177a2a5`.

### 8. CHARS_PER_TOKEN
Для русского договора ориентир **2** символа ≈ 1 токен (`CHARS_PER_TOKEN=2`). При отказах по лимиту — `1`. Параметр int, дробь нельзя без правки кода.

---

## Текущая архитектура (коротко)

| Часть | Как сейчас |
|--------|------------|
| API | Flask `POST /parse`, `X-API-Key` |
| GPT | Lite + async completion + poll |
| Блоки | Динамически от текущего JSON |
| Merge | Плейсхолдеры reject; skip overwrite если false; skip failed block |
| Логи | `logs/app_*.log` + `logs/app_errors_*.log` |
| Промпт системы | `system_prompt.txt` |

Ключевые файлы: `pipeline.py`, `blocking.py`, `yandex_gpt.py`, `schema_state.py`, `logging_setup.py`, `config.py`.

---

## Env на сервере (чеклист)

```
YANDEX_GPT_MODEL=yandexgpt-lite/latest
YANDEX_GPT_API_URL=https://llm.api.cloud.yandex.net/foundationModels/v1/completionAsync
YANDEX_OPERATIONS_API_URL=https://operation.api.cloud.yandex.net/operations
GPT_HTTP_TIMEOUT_SECONDS=60
GPT_ASYNC_TIMEOUT_SECONDS=300
GPT_ASYNC_POLL_INTERVAL_SECONDS=1
CHARS_PER_TOKEN=2
MERGE_ALLOW_OVERWRITE=false   # рекомендуется после soft-skip фикса
```

`.env` не коммитить. Шаблон: `.env.example`.

После обновления кода: `git pull` + перезапуск + сверить `.env`.

---

## Открытые риски

- Async Lite медленный / иногда timeout 300с на операцию.
- Content-filter Яндекса на отдельных фрагментах → поле может остаться `???`.
- Early-exit редко срабатывает, пока есть незаполненные поля (часто `end_date`).
- Dev Flask на публичном IP — сканеры (не баг продукта).
- Имена файлов из Delphi в MIME-encoding — косметика.

---

## Коммиты-ориентиры

- `ef85c6d` / этот файл — continuity  
- `177a2a5` — error logs  
- `8844213` — soft-skip overwrite + skip blocks  
- `296cbdb` — placeholders + early exit  
- `12816a6` — Lite + async  
- `8f58a1f` — packing vs current state  

Транскрипт длинного чата (Cursor): agent-transcripts / `e57b8e8d-bc09-4b7c-b417-05cf9e79cb43`.
