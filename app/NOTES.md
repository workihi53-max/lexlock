# NOTES — веб-слой (app/) и интерфейс lexlock

Заметки о решениях и допущениях веб-слоя. Ядро `lexlock/` не редактируется.

## Расхождения / допущения по интерфейсу lexlock (SPEC §2)

1. **`Agent.run` события.** Форма `Event(kind, data)` заморожена, но *содержимое*
   `data` в SPEC не раскрыто. Веб-слой и фронтенд принимают варианты:
   - `token` → `data.text` (основной), запасные: `content`, `token`;
   - `final` → `data.answer`, запасные: `content`, `message`;
   - `tool_call` → `data.name` + `data.arguments`;
   - `tool_result` → `data.result`, запасной `data.output`;
   - `status` → `data.message`, запасной `data.status`;
   - `error` → `data.message`.
   Если lexlock отдаст другие ключи — поменять парсер в `index.html` (функция `handleEvent`).

2. **`/api/scenario/fill`** (обновлено по SPEC): `filename` необязателен.
   Пустое/отсутствующее имя — легальный режим «пакет»: вызывается
   `lexlock_scenarios.fill_contract(None, out_name)`, ядро берёт все документы
   workspace. Валидация пути применяется только к непустому имени.
   В ответ добавляется `download_name` (голое имя из `out_path`) —
   чтобы фронтенд мог собрать ссылку `/api/download/<имя>` без парсинга путей.
   Остальные поля результата (`fields`, `missing`, `package_mode`, `sources`,
   `log`) передаются как есть.

3. **`/api/files` формат** в SPEC не заморожен. Отдаётся
   `{"files": [{"name","size","ext"}]}` (размер в байтах, `ext` с точкой).

4. **`/api/chat` тело запроса** в SPEC не заморожено. Принято:
   `{"message": str, "history": [{"role","content"}, ...] | null}`.
   `history` передаётся в `Agent.run` как есть.

5. **`/api/health`**: если `LLM.health()` бросает исключение (Ollama не запущена),
   endpoint отвечает `{"ok": true, "ollama": false, "model_installed": false}` —
   приложение живо, модель недоступна.

6. **Загрузка файлов**: имя из multipart очищается от пути
   (`Path(name).name` после замены `\` на `/`), битые имена пропускаются;
   если не сохранился ни один файл — 400.

7. **Валидация имён** (`safe_workspace_path`): запрещены пустые имена, `.`/`..`,
   `/` и `\`, несовпадение `Path(name).name`, симлинки и пути вне workspace
   (проверка через `resolve().is_relative_to(workspace.resolve())`).
   Применяется к `/api/download/{name}` и всем `filename` в сценариях.

## SSE

`/api/chat` стримит `Event` из `Agent.run`: `data: {json}\n\n`, по одной строке на событие.
Генератор `Agent.run` выполняется в фоновом потоке (daemon), события передаются через
`queue.Queue`; асинхронный генератор читает очередь через `asyncio.to_thread(q.get)`,
поэтому uvicorn не блокируется. Исключение внутри агента превращается в событие
`{"kind":"error"}`; завершение потока отмечается SSE-комментарием `: done`.
При обрыве соединения генератор гасится по `CancelledError`, поток умирает как daemon.

## Прочее

- Запуск: `python -m app.server` (или `uvicorn app.server:app`). Стартовый лог —
  по-русски: адрес, модель, режим (офлайн/отладка).
- `enforce_offline()` вызывается в lifespan-старте, если `config.offline`.
- Фронтенд — один файл `static/index.html`, без CDN, шрифтов и внешних запросов.
  Эмодзи только в бейдже офлайн-режима (🔒) и маркерах инструментов (🔧).
