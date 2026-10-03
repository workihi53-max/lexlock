# SPEC — «Ваня» (Legal AI Vault) — демо MVP

> Контракт для всех исполнителей. **Ничего в интерфейсах ниже не менять без правки этого файла.**
> Пользовательские строки — по-русски. Идентификаторы в коде — латиницей.
> Цель: собрать работающее локальное приложение, полностью офлайн после первой установки.

## 0. Целевое железо

- Минимум: 8 ГБ ОЗУ, 4 ядра, ~6 ГБ свободного диска, без GPU.
- Работает через Ollama на `127.0.0.1:11434` (CPU-инференс).
- Модель по умолчанию: `qwen2.5:3b` (`VANYA_MODEL` переопределяет), лёгкая альтернатива `qwen2.5:1.5b`.
- Приложение обязано быть работоспособным, даже если модель недоступна: детерминированные
  сценарии (извлечение реквизитов, заполнение договора) работают без LLM.

## 1. Структура репозитория и владельцы файлов

```
акселетартор2026/
├── SPEC.md                    (готово — Sisyphus)
├── README.md                  [C: скрипты/упаковка]
├── pyproject.toml             [C]
├── .gitignore                 [C]
├── install.sh                 [C]   первичная установка (ставит uv, Ollama, модель)
├── bootstrap.sh               [C]   установка одной командой без git
├── run.sh                     [C]   запуск приложения (офлайн)
├── .github/workflows/ci.yml   [C]   автопроверка тестов на GitHub Actions
├── .github/workflows/release.yml [C] сборка установщиков по тегу v*
├── packaging/                 [C]   .dmg (macOS), AppImage (Linux), Inno Setup (Windows)
├── vanya/                     [A: ядро]
│   ├── __init__.py
│   ├── config.py
│   ├── offline.py
│   ├── llm.py
│   ├── docs.py
│   ├── extract.py
│   ├── rag.py                    подбор релевантных фрагментов под запрос
│   ├── cache.py                  дисковый кэш ответов LLM
│   ├── ocr.py                    локальный OCR (Tesseract, русский)
│   ├── checklists.py             чек-листы договоров по типам
│   ├── tools.py
│   ├── agent.py
│   ├── scenarios.py
│   └── prompts.py
├── app/                       [B: веб-слой]
│   ├── server.py
│   └── static/index.html
├── scripts/                   [C]
│   ├── check_ram.py
│   ├── make_template.py
│   └── demo_data.py           (наполнение templates/ и samples/)
├── templates/                 [C]   (генерируется scripts/make_template.py)
│   └── dogovor_template.docx
├── samples/                   [D: mistral]   тестовый пакет документов
│   ├── 01_pasport_vypiska.txt
│   ├── 02_rekvizity_ooo.txt
│   └── 03_dogovor_riski.txt
└── tests/
    ├── test_extract.py        [A]
    ├── test_docs.py           [A]
    ├── test_tools.py          [A]
    ├── test_agent.py          [A]   (с mock-LLM, без Ollama)
    └── test_server.py         [B]   (FastAPI TestClient, без Ollama)
```

Рабочее пространство пользователя (не в репо): `./workspace/` (переопределяется `VANYA_WORKSPACE`).

## 2. Замороженные интерфейсы

### 2.1 `vanya/config.py`

```python
@dataclass(frozen=True)
class Config:
    model: str          # env VANYA_MODEL, default "qwen2.5:3b"
    ollama_url: str     # env VANYA_OLLAMA_URL, default "http://127.0.0.1:11434"
    workspace: Path     # env VANYA_WORKSPACE, default <repo>/workspace
    port: int           # env VANYA_PORT, default 8765
    offline: bool       # env VANYA_OFFLINE, default True (strict: блокирует не-loopback сокеты)
    max_ctx_chars: int  # default 12000 — сколько символов документов кладём в промпт

def load_config() -> Config: ...
```

### 2.2 `vanya/offline.py`

```python
def enforce_offline() -> None:
    """Разрешает connect()/getaddrinfo() только для 127.0.0.1/localhost/::1.
    Иначе — ConnectionError. Идемпотентно. Вызывается из run.sh и app/server.py."""
```

### 2.3 `vanya/llm.py`

```python
@dataclass
class ToolCall:
    name: str
    arguments: dict

@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCall]

class LLMError(RuntimeError): ...

class LLM:
    def __init__(self, config: Config | None = None, timeout: float = 300.0) -> None: ...
    def available(self) -> bool: ...           # GET /api/tags, True если модель есть
    def health(self) -> dict: ...              # {"ok": bool, "model": str, "installed": bool, "error": str|None}
    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult: ...
    def stream(self, messages: list[dict]) -> Iterator[str]: ...   # чанки текста
    def json_chat(self, messages: list[dict], schema_hint: str = "") -> dict:
        """Просит строгий JSON, парсит первый {...} устойчиво. При неудаче — LLMError."""
```

### 2.4 `vanya/docs.py`

```python
TEXT_EXT = {".txt", ".md", ".csv", ".json"}
def read_document(path: str | Path) -> str: ...            # .txt/.md/.docx/.pdf, иначе raise ValueError
def read_folder(folder: str | Path, limit_chars: int = 20000) -> str:
    """Конкатенация: '=== <имя файла> ===\n<текст>'. Нетекстовые/битые — пропускает."""
def write_text(path: str | Path, content: str) -> Path: ...
def fill_docx(template: str | Path, values: dict[str, str], out_path: str | Path) -> Path:
    """Заменяет {{key}} (в т.ч. разорванные по runs) и {{key}}→'' в таблицах/колонтитулах.
    Возвращает путь результата."""
def docx_placeholders(template: str | Path) -> list[str]: ...
```

### 2.5 `vanya/extract.py`

Только регулярки + нормализация, **без LLM**.

```python
FIELDS = ("familiya","imya","otchestvo","fio","data_rozhdeniya","pasport_seriya","pasport_nomer",
          "pasport_vydan","pasport_data","pasport_kod","adres_registracii","inn","ogrn","kpp",
          "organizaciya","yuridicheskiy_adres","bank","bik","raschetny_schet","korr_schet",
          "telefon","email","dolzhnost","data_dogovora","nomer_dogovora","summa")

def extract_requisites(text: str) -> dict[str, str]:
    """Возвращает только найденные ключи (значения — обрезанные строки)."""

def missing_fields(found: dict[str, str]) -> list[str]: ...
```

### 2.6 `vanya/tools.py`

```python
@dataclass
class Tool:
    name: str
    description: str          # по-русски, для модели
    parameters: dict          # JSON Schema
    fn: Callable[..., dict]

TOOLS: list[Tool]             # ровно 6 штук, см. таблицу ниже
def tool_schemas() -> list[dict]: ...       # формат Ollama: {"type":"function","function":{...}}
def dispatch(name: str, arguments: dict) -> dict:
    """Возвращает {"ok": True, "result": ...} либо {"ok": False, "error": "..."}.
    Никогда не бросает исключение наружу."""
```

| name | args | что делает |
|---|---|---|
| `list_files` | `{}` | список файлов в workspace (`[{name,size,ext}]`) |
| `read_document` | `{"filename": str}` | текст документа из workspace |
| `extract_requisites` | `{"filename": str}` | реквизиты из документа (детерминированно) |
| `fill_contract` | `{"source_filename": str?, "out_name": str?}` | извлекает реквизиты и заполняет `templates/dogovor_template.docx`, кладёт в workspace. `source_filename` пустой/отсутствует → режим «пакет»: берутся ВСЕ документы workspace |
| `find_risks` | `{"filename": str}` | LLM-анализ рисков договора → `{"summary","risks":[...]}` |
| `write_report` | `{"name": str, "content": str}` | сохраняет текстовый отчёт в workspace |

### 2.7 `vanya/agent.py`

```python
@dataclass
class Event:
    kind: str      # "status" | "tool_call" | "tool_result" | "token" | "final" | "error"
    data: dict

class Agent:
    def __init__(self, llm=None, max_steps: int = 6, system: str | None = None) -> None: ...
    def run(self, user_message: str, history: list[dict] | None = None) -> Iterator[Event]: ...
    def run_sync(self, user_message: str, history: list[dict] | None = None) -> Event: ...
```

Правила цикла: `LLM.chat(messages, tools=tool_schemas())`; если есть `tool_calls` — выполнить
через `dispatch`, добавить `role="tool"` сообщения, повторить (не больше `max_steps`); иначе —
финальный ответ. Любая ошибка LLM → `Event("error", ...)`, приложение не падает.

### 2.8 `vanya/scenarios.py`

Перед отправкой в LLM документ режется не по первым `max_ctx_chars`, а через
`rag.select_relevant(text, query, max_ctx_chars)` — подбор релевантных абзацев.
Успешные ответы `find_risks`/`ask` кэшируются на диск (`cache.py`, ключ — хеш
модели + текста документа + вопроса); повторный вызов мгновенный. При отключённом
кэше (`VANYA_CACHE=0`) поведение прежнее, только без ускорения.

```python
def fill_contract(source_filename: str | None = None, out_name: str | None = None) -> dict
    # source_filename = имя файла в workspace; None / "" / "-" → режим «пакет»:
    #   склейка ВСЕХ документов workspace через docs.read_folder()
    # {"ok": True, "out_path": str, "fields": {...}, "missing": [...], "log": [str,...]}
    # В результат добавить "package_mode": bool и "sources": [имена использованных файлов]
def find_risks(filename: str) -> dict
    # {"ok": True, "summary": str, "risks": [{"punkt","risk","level","recommendation"}], "log":[...],
    #  "fallback": bool, "cached": bool}  — если LLM недоступна, отдаёт эвристический список и fallback=True
def ask(filename: str, question: str) -> dict
    # {"ok": True, "answer": str, "cached": bool}
def export_risks(filename: str) -> dict
    # find_risks() + сохранение отчёта в .docx: {"ok": True, "out_path": str,
    #  "download_name": str, "risks": [...], "fallback": bool}
def check_contract(filename: str, contract_type: str | None = None) -> dict
    # проверка по чек-листу; тип определяется автоматически или задан вручную:
    # {"ok": True, "contract_type": str, "items": [{"code","item","present"}],
    #  "missing": [str], "score": int}  — детерминированно, без LLM
```

Если задан `VANYA_LLM_EXTRACT=1`, `fill_contract` дозаполняет ненайденные поля
через LLM и возвращает их имена в `model_fields`; при недоступной модели поведение
остаётся детерминированным (инвариант 2).

### 2.9 Веб-API (`app/server.py`, FastAPI, uvicorn, порт из конфига)

| метод | путь | назначение |
|---|---|---|
| GET | `/` | `static/index.html` |
| GET | `/api/health` | `{"ok","model","model_installed","offline","ollama","workspace"}` |
| GET | `/api/files` | список файлов workspace |
| POST | `/api/upload` | multipart `files` → сохраняет в workspace → `{"saved":[...]}`. Один файл ≤ 25 МБ, иначе 413 |
| POST | `/api/scenario/fill` | `{"filename"?,"out_name"?}` → результат `scenarios.fill_contract`. Пустой/отсутствующий `filename` = режим «пакет» (все документы) |
| POST | `/api/scenario/risks` | `{"filename"}` → `scenarios.find_risks` |
| POST | `/api/scenario/export_risks` | `{"filename"}` → `scenarios.export_risks` (отчёт `.docx`) |
| POST | `/api/scenario/checklist` | `{"filename","contract_type"?}` → `scenarios.check_contract` (чек-лист) |
| POST | `/api/scenario/ask` | `{"filename","question"}` → `scenarios.ask` |
| POST | `/api/chat` | SSE-поток `Event` из `Agent.run` (JSON-строки, `data: {...}\n\n`) |
| GET | `/api/download/{name}` | отдаёт файл из workspace |

Статика: одна страница `index.html`, vanilla JS, без CDN и внешних шрифтов (офлайн!).
Тёмно-серая/тёплая палитра, крупные элементы. Бейдж «🔌 Офлайн-режим» + имя модели.

### 2.10 Скрипты

- `install.sh` — сам ставит `uv` и Ollama, если их нет (macOS: Homebrew/Ollama.app,
  Linux: официальный скрипт), затем `uv venv --python 3.12 .venv`, `uv pip install -e .`,
  проверка ОЗУ (`scripts/check_ram.py`), `ollama pull $VANYA_MODEL` (можно `--skip-model`),
  генерация шаблона/сэмплов. Идемпотентен. `bootstrap.sh` — установка одной командой без git.
- `run.sh` — активирует venv, `VANYA_OFFLINE=1` по умолчанию, стартует `python -m app.server`,
  печатает URL и открывает браузер. Флаги `--no-offline` и `--no-browser`.
- `scripts/check_ram.py` — печатает ОЗУ/swap/диск/ядра, предупреждает при <3 ГБ свободно,
  возвращает 0/1 (1 — рискованно для запуска модели). `--recommend` печатает модель
  по свободной ОЗУ: `qwen2.5:3b` при ≥5 ГБ, иначе `qwen2.5:1.5b`.
- `packaging/` — сборка установщиков «для людей» (без терминала): macOS — `.app` в `.dmg`
  (`macos/build_dmg.sh`), Linux — AppImage с zenity/kdialog (`linux/build_appimage.sh`),
  Windows — Inno Setup + `run.vbs` без консоли (`windows/`). Все ставят uv/Ollama/модель
  при первом запуске. Автосборка — `.github/workflows/release.yml` по тегу `v*`.
- `scripts/make_template.py` — создаёт `templates/dogovor_template.docx` (договор оказания
  услуг: шапка, реквизиты через `{{...}}`, разделы 1–7, подписи). Плейсхолдеры строго из `FIELDS`.
- `scripts/demo_data.py` — создаёт `samples/*` если их нет (текст — из задач [D]).

## 3. Общие требования

| Python 3.12 (venv), зависимости: `fastapi`, `uvicorn`, `httpx`, `python-docx`, `pypdf`,
  `python-multipart`, `pytest`. OCR — `pymupdf` (extra `[ocr]`) и системный Tesseract с
  языком `rus`. Никаких тяжёлых ML-библиотек (без torch/transformers).
- Полный набор зависимостей ≤ 150 МБ.
- Никаких обращений в интернет из кода приложения. Только `127.0.0.1`.
- Строки для пользователя — русские, короткие, без эмодзи в служебных сообщениях.
- Тесты не требуют Ollama: LLM замокан. Sсенарии с LLM тестируются на monkeypatch.
- Комментарии — кратко, по-русски, только там где неочевидно.
- Не трогать файлы, принадлежащие другому исполнителю (см. §1).

## 4. Проверка готовности (definition of done)

1. `python -m pytest tests -q` — зелёный без Ollama.
2. `bash run.sh` поднимает сервер, `/api/health` отвечает.
3. Сценарий `fill_contract` заполняет шаблон на тестовых данных (проверяется тестом).
4. `python scripts/check_ram.py` корректно отрабатывает на машине с 8 ГБ.
5. Отключённый интернет не влияет на работу приложения (strict offline не даёт утечки).
