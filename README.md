# DocumentDataParse API

Инструкция по обращению к HTTP API: извлечение реквизитов из **PDF/DOCX** (в т.ч. сканов через OCR) и из **печатной формы договора** на zakupki.gov.ru (ФЗ-223).

Клиент (в т.ч. **Delphi**) отправляет `multipart/form-data` + `prompt`, получает JSON с полями.

Базовый URL (пример): `http://<host>:8000`

---

## Эндпоинты

| Метод | Путь | Описание |
|--------|------|----------|
| `POST` | `/parse` | Разбор одного или нескольких загруженных файлов (PDF/DOCX) |
| `POST` | `/get_document_data` | Поиск договора на zakupki.gov.ru по `document_id` → печатная форма → те же поля по `prompt` |

Оба эндпоинта используют один и тот же формат ответа и один и тот же `prompt` (JSON-каркас).

---

## Авторизация

В каждом запросе обязателен заголовок:

```http
X-API-Key: <ключ_доступа>
```

Ключ задаётся на сервере в `APP_API_KEY` (файл `.env`).  
При неверном или отсутствующем ключе: **HTTP 401**.

```json
{ "detail": "Invalid or missing API key" }
```

---

## Общие правила входа

### Content-Type

**`multipart/form-data`**.  
Не JSON-body. Для `/get_document_data` файлов нет — поля формы текстовые, но формат тот же multipart.

### Общие поля

| Имя поля | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `username` | text | да | Имя/логин вызывающей системы (для логов) |
| `prompt` | text | да | Промпт с JSON-каркасом полей (см. ниже) |

### Промпт (`prompt`)

Текст + **обязательный JSON-объект в фигурных скобках `{ ... }`**.  
Сервер вытаскивает объект как каркас: значения заменяются на `"???"` и заполняются по ходу разбора.

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

Готовые шаблоны:

| Файл | Назначение |
|------|------------|
| `prompt.txt` / `Prompt.txt` | Договор |
| `Prompt_dop.txt` | Доп. соглашение |
| `Prompt_akt.txt` | Акт выполненных работ |

Правила заполнения `"???"` задаются **на сервере** (`system_prompt.txt`); в клиентский `prompt` их дублировать не нужно.

**Delphi / Indy:** для `prompt` и `username` задайте `ContentTransfer := '8bit'`, иначе кириллица уходит как quoted-printable (`=D0=A2...`). Подробнее: `DELPHI_PROMPT_UTF8.txt`.

---

## `POST /parse` — файлы

### Поля формы

| Имя поля | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `username` | text | да | см. выше |
| `prompt` | text | да | см. выше |
| `files` | file | да | Один или несколько файлов. **Имя поля всегда `files`** |

### Файлы

- Расширения: `.pdf`, `.docx`
- Несколько файлов — несколько частей `files` в одном запросе
- Каждый файл → отдельный элемент `results[]`

### Пример запроса

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

### curl

```bash
curl -X POST "http://127.0.0.1:8000/parse" \
  -H "X-API-Key: change-me-strong-secret" \
  -F "username=test" \
  -F "prompt=@prompt.txt;type=text/plain" \
  -F "files=@dogovor.pdf;type=application/pdf"
```

---

## `POST /get_document_data` — zakupki.gov.ru

Сервер по `document_id` открывает поиск в реестре договоров ФЗ-223 (`searchString`), требует **ровно одну** карточку, скачивает **печатную форму**, извлекает текст и прогоняет через тот же GPT-пайплайн, что и файлы.

Логин на сайте не нужен.

### Поля формы

| Имя поля | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `username` | text | да | см. выше |
| `prompt` | text | да | тот же каркас, что для договора |
| `document_id` | text | да | Значение для `searchString` (например номер договора `32616026950`) |

Файлы **не** передаются.

### Пример запроса

```http
POST /get_document_data HTTP/1.1
Host: 127.0.0.1:8000
X-API-Key: change-me-strong-secret
Content-Type: multipart/form-data; boundary=----Boundary

------Boundary
Content-Disposition: form-data; name="username"

delphi-client
------Boundary
Content-Disposition: form-data; name="prompt"

Тип документа: договор.
{ "contract_number": "???", "contract_date": "???", "contract_price": "???" }
------Boundary
Content-Disposition: form-data; name="document_id"

32616026950
------Boundary--
```

### curl

```bash
curl -X POST "http://127.0.0.1:8000/get_document_data" \
  -H "X-API-Key: change-me-strong-secret" \
  -F "username=test" \
  -F "prompt=@prompt.txt;type=text/plain" \
  -F "document_id=32616026950"
```

### Консольный тест

```bash
python test_get_document_data.py
```

Ввод `document_id` в консоль → JSON-ответ в консоль (нужны поднятый API и `.env` с `APP_API_KEY`).

### Ошибки именно этого эндпоинта

| HTTP | Когда | Тело (пример) |
|------|--------|----------------|
| 400 | 0 или >1 карточек в поиске / нет ссылки на печать | `{"detail":"Found 2 registry cards..."}` |
| 400 | Нет `document_id` / `username` / `prompt` | `{"detail":"document_id is required"}` |
| 502 | Сеть/SSL до zakupki.gov.ru | `{"detail":"Failed to fetch document from zakupki.gov.ru: ..."}` |

Если в логах/ответе `CERTIFICATE_VERIFY_FAILED`, на сервере в `.env`:

```env
ZAKUPKI_SSL_VERIFY=false
```

(сайт по HTTPS; падает проверка цепочки сертификатов — часто антивирус/прокси.)

---

## Формат ответа (оба эндпоинта)

### Успех

- **HTTP 200**, `Content-Type: application/json`, UTF-8

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

Для `/get_document_data` обычно один элемент:

- `filename` — `zakupki:<document_id>`
- `text_source` — `zakupki_print:<url печатной формы>`
- `extension` — `.html`

### Поля верхнего уровня

| Поле | Тип | Описание |
|------|-----|----------|
| `request_id` | string | ID запроса (логи / поддержка) |
| `username` | string | То же, что во входе |
| `results` | array | По файлу или по одному веб-документу |

### Элемент `results[]`

| Поле | Тип | Описание |
|------|-----|----------|
| `filename` | string | Имя файла или `zakupki:<id>` |
| `success` | bool | Разбор прошёл / нет |
| `fields` | object \| null | Поля по каркасу `prompt`; при ошибке обычно `null` |
| `meta` | object | Техсведения |

`"???"` в `fields` = поле **не найдено** (не путать с JSON `null`).

### `meta`

| Поле | Тип | Описание |
|------|-----|----------|
| `size_bytes` | int | Размер файла / объём текста |
| `extension` | string | `.pdf` / `.docx` / `.html` |
| `content_type` | string \| null | MIME |
| `text_source` | string \| null | `docx`, `pdf_text:...`, `vision:...`, `zakupki_print:...` |
| `page_count` | int \| null | Страницы PDF (для веб — обычно `null`) |
| `gpt_attempts` | int \| null | Сумма попыток GPT |
| `duration_ms` | int \| null | Время обработки, мс |
| `error` | string \| null | Если `success = false` |

HTTP **200** возможен при `success: false` внутри `results` (для `/parse` по отдельным файлам). Смотрите каждый элемент.

### Общие ошибки запроса

| HTTP | Когда | Тело (пример) |
|------|--------|----------------|
| 401 | Нет/неверный `X-API-Key` | `{"detail":"Invalid or missing API key"}` |
| 400 | Нет обязательных полей формы | `{"detail":"username is required"}` |

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

Рекомендуется **Indy**: `TIdHTTP` + `TIdMultiPartFormDataStream`.

### `/parse` — файлы

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
  F: TIdFormDataField;
begin
  HTTP := TIdHTTP.Create(nil);
  Form := TIdMultiPartFormDataStream.Create;
  ResponseStream := TStringStream.Create('', TEncoding.UTF8);
  SSL := nil;
  try
    // Для HTTPS:
    // SSL := TIdSSLIOHandlerSocketOpenSSL.Create(HTTP);
    // HTTP.IOHandler := SSL;
    // SSL.SSLOptions.Method := sslvTLSv1_2;

    HTTP.Request.CustomHeaders.Values['X-API-Key'] := AApiKey;
    HTTP.ReadTimeout := 600000;
    HTTP.ConnectTimeout := 30000;

    F := Form.AddFormField('username', AUsername, 'utf-8');
    F.ContentTransfer := '8bit';
    F := Form.AddFormField('prompt', APrompt, 'utf-8');
    F.ContentType := 'text/plain; charset=utf-8';
    F.ContentTransfer := '8bit';

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

### `/get_document_data` — document_id

```delphi
function GetDocumentData(
  const ABaseUrl, AApiKey, AUsername, APrompt, ADocumentId: string
): string;
var
  HTTP: TIdHTTP;
  Form: TIdMultiPartFormDataStream;
  ResponseStream: TStringStream;
  F: TIdFormDataField;
begin
  HTTP := TIdHTTP.Create(nil);
  Form := TIdMultiPartFormDataStream.Create;
  ResponseStream := TStringStream.Create('', TEncoding.UTF8);
  try
    HTTP.Request.CustomHeaders.Values['X-API-Key'] := AApiKey;
    HTTP.ReadTimeout := 600000;
    HTTP.ConnectTimeout := 30000;

    F := Form.AddFormField('username', AUsername, 'utf-8');
    F.ContentTransfer := '8bit';
    F := Form.AddFormField('prompt', APrompt, 'utf-8');
    F.ContentType := 'text/plain; charset=utf-8';
    F.ContentTransfer := '8bit';
    Form.AddFormField('document_id', ADocumentId, 'utf-8');

    HTTP.Post(
      ABaseUrl.TrimRight(['/']) + '/get_document_data',
      Form,
      ResponseStream
    );
    Result := ResponseStream.DataString;
  finally
    ResponseStream.Free;
    Form.Free;
    HTTP.Free;
  end;
end;
```

### Разбор ответа

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
        // meta.error
        Continue;
      end;
      Fields := Item.GetValue<TJSONObject>('fields');
      if Fields <> nil then
        ContractNumber := Fields.GetValue<string>('contract_number'); // может быть "???"
    end;
  finally
    Root.Free;
  end;
end;
```

### Важно для Delphi

1. Для `/parse` имя поля файла — всегда **`files`**.
2. Для `/get_document_data` поле **`document_id`**, файлов нет.
3. `prompt` / `username`: `ContentTransfer := '8bit'` (иначе quoted-printable).
4. Таймаут большой (минуты): OCR / GPT / запрос к zakupki.
5. Проверяйте `success` у каждого `results[]`, не только HTTP-код.
6. `"???"` — строка «не найдено», не JSON `null`.

---

## Краткий алгоритм на сервере

### `/parse`

1. Проверка ключа, `username`, `prompt`, файлов.
2. Из `prompt` — JSON-каркас со значениями `"???"`.
3. Текст документа → атомы (страницы / абзацы / Vision OCR).
4. Блоки → YandexGPT → merge полей.
5. JSON в ответе; файлы и сырой текст на диске не хранятся.

### `/get_document_data`

1. Проверка ключа, `username`, `prompt`, `document_id`.
2. Поиск на zakupki.gov.ru → ровно 1 карточка → HTML печатной формы → текст.
3. Тот же GPT-пайплайн, что для файлов.
4. Ответ в том же формате (`results` из одного элемента).

---

## Запуск сервера (справка)

```bash
cp .env.example .env   # APP_API_KEY, YANDEX_API_KEY, YANDEX_FOLDER_ID
pip install -r requirements.txt
python -m app.main
```

Слушает `0.0.0.0:8000` (см. `app/main.py`).

Тесты:

- GUI файлов: `python utils/gui_client.py`
- zakupki: `python test_get_document_data.py`