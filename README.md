# DocumentDataParse API

HTTP API для извлечения реквизитов из документов **PDF** и **DOCX** (в том числе сканов PDF через OCR).  
Клиент (в т.ч. **Delphi**) отправляет файлы и текст промпта, получает JSON с полями по каждому файлу.

Базовый URL (пример): `http://<host>:8000`

---

## Эндпоинт

| Метод | Путь | Описание |
|--------|------|----------|
| `POST` | `/parse` | Разбор одного или нескольких документов |

Других публичных эндпоинтов нет.

---

## Авторизация

В каждом запросе обязателен заголовок:

```http
X-API-Key: <ключ_доступа>
```

Ключ задаётся на сервере в переменной окружения `APP_API_KEY` (файл `.env`).  
При неверном или отсутствующем ключе: **HTTP 401**.

```json
{ "detail": "Invalid or missing API key" }
```

---

## Как подавать данные (вход)

### Content-Type

Только **`multipart/form-data`** (как загрузка файлов в браузере).  
Не JSON-body и не `application/x-www-form-urlencoded` для файлов.

### Поля формы

| Имя поля | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `username` | text | да | Имя/логин вызывающей системы или пользователя (для логов) |
| `prompt` | text | да | Промпт с JSON-каркасом полей (см. ниже) |
| `files` | file | да | Один или несколько файлов. **Имя поля формы всегда `files`** (повторяется для каждого файла) |

### Файлы

- Допустимые расширения: `.pdf`, `.docx`
- Можно отправить несколько файлов в одном запросе
- Каждый файл обрабатывается отдельно; в ответе — массив `results`

### Промпт (`prompt`)

Текст на русском/любом языке + **обязательный JSON-объект в фигурных скобках `{ ... }`**.  
Сервер вытаскивает этот объект как каркас результата: все значения в каркасе заменяются на `"???"` и по ходу разбора заполняются.

Рекомендуемый вид:

```text
Тип документа: договор.
Извлеки реквизиты по каркасу ниже.

{
  "contract_number": "???",
  "contract_date": "???",
  ...
}

Смысл полей:
- contract_number — номер договора
...
```

Готовые шаблоны в репозитории:

| Файл | Назначение |
|------|------------|
| `prompt.txt` / `Prompt.txt` | Договор |
| `Prompt_dop.txt` | Доп. соглашение |
| `Prompt_akt.txt` | Акт выполненных работ |

Правила заполнения `"???"` / осторожной перезаписи задаются **на сервере** (system prompt), в клиентский `prompt` их дублировать не нужно — достаточно типа документа, каркаса и описания полей.

### Пример HTTP-запроса (схема)

```http
POST /parse HTTP/1.1
Host: 127.0.0.1:8000
X-API-Key: change-me-strong-secret
Content-Type: multipart/form-data; boundary=----Boundary

------Boundary
Content-Disposition: form-data; name="username"

delphi-client
------Boundary
Content-Disposition: form-data; name="prompt"

Тип документа: договор.
{ "contract_number": "???", "contract_date": "???" }
------Boundary
Content-Disposition: form-data; name="files"; filename="dogovor.pdf"
Content-Type: application/pdf

<бинарные данные файла>
------Boundary--
```

---

## Как забирать данные (выход)

### Успешный ответ

- **HTTP 200**
- `Content-Type: application/json`
- Кодировка UTF-8

### Структура JSON

```json
{
  "request_id": "uuid-запроса",
  "username": "delphi-client",
  "results": [
    {
      "filename": "dogovor.pdf",
      "success": true,
      "fields": {
        "contract_number": "123/2024",
        "contract_date": "01.02.2024",
        "end_date": "???",
        "contract_name": "...",
        "object_name": "...",
        "object_address": "...",
        "work_types": "...",
        "customer_name": "...",
        "customer_inn": "...",
        "executor_name": "...",
        "executor_inn": "...",
        "works_cost": "...",
        "contract_price": "..."
      },
      "meta": {
        "size_bytes": 615333,
        "extension": ".pdf",
        "content_type": "application/pdf",
        "text_source": "pdf_text:embedded_text",
        "page_count": 12,
        "gpt_attempts": 3,
        "duration_ms": 45210,
        "error": null
      }
    }
  ]
}
```

### Поля верхнего уровня

| Поле | Тип | Описание |
|------|-----|----------|
| `request_id` | string | Уникальный ID запроса (для логов/поддержки) |
| `username` | string | То же, что передали во входе |
| `results` | array | Результат **по каждому** загруженному файлу |

### Элемент `results[]`

| Поле | Тип | Описание |
|------|-----|----------|
| `filename` | string | Имя файла, как в multipart |
| `success` | bool | `true` — разбор прошёл; `false` — ошибка по этому файлу |
| `fields` | object \| null | Извлечённые поля (каркас из `prompt`). При ошибке обычно `null` |
| `meta` | object | Технические сведения |

Значение `"???"` в `fields` означает: поле в документе **не найдено** (или не уверенно извлечено).

### `meta`

| Поле | Тип | Описание |
|------|-----|----------|
| `size_bytes` | int | Размер файла |
| `extension` | string | Например `.pdf` |
| `content_type` | string \| null | MIME, если передан клиентом |
| `text_source` | string \| null | Откуда текст: `docx`, `pdf_text:...`, `vision:...` |
| `page_count` | int \| null | Число страниц (PDF) |
| `gpt_attempts` | int \| null | Суммарные попытки вызовов GPT по файлу |
| `duration_ms` | int \| null | Время обработки файла, мс |
| `error` | string \| null | Текст ошибки, если `success = false` |

Важно: HTTP **200** может прийти даже если один из файлов упал (`success: false`). Смотрите каждый элемент `results`.

### Ошибки запроса целиком

| HTTP | Когда | Тело (пример) |
|------|--------|----------------|
| 401 | Нет/неверный `X-API-Key` | `{"detail":"Invalid or missing API key"}` |
| 400 | Нет `username` / `prompt` / файлов | `{"detail":"username is required"}` и т.п. |

---

## Каркасы полей (готовые промпты)

### Договор (`prompt.txt`)

`contract_number`, `contract_date`, `end_date`, `contract_name`, `object_name`, `object_address`, `work_types`, `customer_name`, `customer_inn`, `executor_name`, `executor_inn`, `works_cost`, `contract_price`

### Доп. соглашение (`Prompt_dop.txt`)

`contract_number`, `contract_date`, `addendum_number`, `addendum_date`

### Акт выполненных работ (`Prompt_akt.txt`)

`contract_number`, `contract_date`, `act_number`, `act_date`, `works_amount`

---

## Вызов из Delphi

Рекомендуется **Indy**: `TIdHTTP` + `TIdMultiPartFormDataStream` (пакет Indy обычно уже в RAD Studio).

### Минимальный пример (Delphi)

```delphi
uses
  System.SysUtils, System.Classes, System.IOUtils,
  IdHTTP, IdMultipartFormData, IdSSLOpenSSL;

function ParseDocuments(
  const ABaseUrl, AApiKey, AUsername, APrompt: string;
  const AFilePaths: TArray<string>
): string;
var
  HTTP: TIdHTTP;
  Form: TIdMultiPartFormDataStream;
  SSL: TIdSSLIOHandlerSocketOpenSSL;
  Path: string;
  ResponseStream: TStringStream;
begin
  HTTP := TIdHTTP.Create(nil);
  Form := TIdMultiPartFormDataStream.Create;
  ResponseStream := TStringStream.Create('', TEncoding.UTF8);
  SSL := nil;
  try
    // Для HTTPS раскомментируйте:
    // SSL := TIdSSLIOHandlerSocketOpenSSL.Create(HTTP);
    // HTTP.IOHandler := SSL;
    // SSL.SSLOptions.Method := sslvTLSv1_2;

    HTTP.Request.CustomHeaders.Values['X-API-Key'] := AApiKey;
    HTTP.ReadTimeout := 600000;  // длинные документы / OCR / GPT
    HTTP.ConnectTimeout := 30000;

    Form.AddFormField('username', AUsername, 'utf-8');
    Form.AddFormField('prompt', APrompt, 'utf-8').ContentType := 'text/plain; charset=utf-8';

    for Path in AFilePaths do
      Form.AddFile('files', Path);  // имя поля именно "files"

    HTTP.Post(ABaseUrl.TrimRight(['/']) + '/parse', Form, ResponseStream);
    Result := ResponseStream.DataString;
  finally
    ResponseStream.Free;
    Form.Free;
    SSL.Free;
    HTTP.Free;
  end;
end;
```

Разбор ответа: любой JSON-парсер (например `System.JSON`):

```delphi
uses System.JSON;

procedure HandleResponse(const AJsonText: string);
var
  Root, Item, Fields: TJSONObject;
  Results: TJSONArray;
  I: Integer;
  Success: Boolean;
  Filename, ContractNumber: string;
begin
  Root := TJSONObject.ParseJSONValue(AJsonText) as TJSONObject;
  if Root = nil then
    raise Exception.Create('Invalid JSON');
  try
    Results := Root.GetValue<TJSONArray>('results');
    for I := 0 to Results.Count - 1 do
    begin
      Item := Results.Items[I] as TJSONObject;
      Filename := Item.GetValue<string>('filename');
      Success := Item.GetValue<Boolean>('success');
      if not Success then
      begin
        // ошибка файла: Item.GetValue<TJSONObject>('meta').GetValue<string>('error')
        Continue;
      end;
      Fields := Item.GetValue<TJSONObject>('fields');
      if Fields <> nil then
        ContractNumber := Fields.GetValue<string>('contract_number'); // может быть "???"
      // ... остальные поля по каркасу промпта
    end;
  finally
    Root.Free;
  end;
end;
```

### Важно для Delphi

1. Имя поля файла — всегда **`files`** (не `file`, не `document`).
2. Несколько файлов — несколько частей `files` в одном multipart.
3. Промпт и username лучше отдавать в UTF-8.
4. Таймаут поставьте большим (минуты): PDF со сканами + несколько блоков GPT.
5. Проверяйте `success` у каждого элемента `results`, а не только HTTP-код.
6. `"???"` — валидное строковое значение «не найдено», не путать с JSON `null`.

### curl (для проверки вне Delphi)

```bash
curl -X POST "http://127.0.0.1:8000/parse" \
  -H "X-API-Key: change-me-strong-secret" \
  -F "username=test" \
  -F "prompt=@prompt.txt;type=text/plain" \
  -F "files=@dogovor.pdf;type=application/pdf"
```

---

## Краткий алгоритм на сервере (для понимания ответа)

1. Проверка `X-API-Key`, `username`, `prompt`, файлов.
2. Из `prompt` извлекается JSON-каркас → стартовое состояние со значениями `"???"`.
3. Документ режется на атомы (страницы PDF / абзацы и таблицы DOCX), атомы упаковываются в блоки под лимит контекста.
4. Блоки по очереди отправляются в YandexGPT вместе с текущим JSON-состоянием.
5. Поля `"???"` заполняются; уже найденные могут быть осторожно уточнены.
6. В ответ клиенту уходит итоговый JSON по каждому файлу. Сами файлы и сырой текст на диске не хранятся.

---

## Запуск сервера (справка)

```bash
cp .env.example .env   # заполнить APP_API_KEY, YANDEX_API_KEY, YANDEX_FOLDER_ID
pip install -r requirements.txt
python -m app.main
```

Слушает `0.0.0.0:8000` (см. `app/main.py`).

Тестовый GUI: `python utils/gui_client.py`.
