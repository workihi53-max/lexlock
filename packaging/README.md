# Установщики «ЛексЛока»

Цель упаковки — чтобы **юрист без опыта** скачал один файл и запустил приложение,
ни разу не открыв терминал (см. «Принципы установки» в `AGENTS.md`).

| Система | Файл | Как ставит пользователь | Сборка |
|---|---|---|---|
| macOS | `LexLock-<версия>.dmg` | открыть `.dmg` → перетащить «ЛексЛок» в «Программы» → запустить | `bash packaging/macos/build_dmg.sh` |
| Linux | `LexLock-<версия>-<арх>.AppImage` | сделать файл исполняемым → двойной клик | `bash packaging/linux/build_appimage.sh` |
| Windows | `LexLock-<версия>-win-setup.exe` | обычный установщик с кнопкой «Далее» | `iscc packaging/windows/installer.iss` |

Первый запуск скачивает Ollama и модель (~2 ГБ) — дальше приложение работает офлайн.

## macOS — настоящий `.app`, без терминала

`build_dmg.sh` собирает `ЛексЛок.app` (нативные диалоги через `osascript`) и красивый `.dmg`
с ярлыком «Программы» для перетаскивания. Пользователь видит только диалоги:
«Продолжить» → уведомление об установке → автоматически открывается браузер.
Журнал установки: `~/Library/Logs/LexLock.log`. Проект разворачивается в
`~/Library/Application Support/LexLock` (бандл `.app` может быть read-only).

**Первый запуск и Gatekeeper.** Приложение пока не подписано Apple, поэтому при первом
запуске macOS может сказать «не удалось проверить разработчика». Нужно один раз нажать на
«ЛексЛок» правой кнопкой → «Открыть» → «Открыть». Это же написано в файле «Как открыть.txt»
внутри `.dmg`. После подписи/нотаризации шаг исчезнет.

```bash
bash packaging/macos/build_dmg.sh   # → dist/LexLock-0.2.0.dmg
```

## Linux — AppImage с диалогами

`AppRun` показывает прогресс через `zenity`/`kdialog` (если есть в системе), ставит
компоненты и сам открывает браузер. Проект разворачивается в `~/lexlock`.

```bash
bash packaging/linux/build_appimage.sh   # → dist/LexLock-0.2.0-x86_64.AppImage
chmod +x LexLock-0.2.0-x86_64.AppImage && ./LexLock-0.2.0-x86_64.AppImage
```

## Windows — установщик с ярлыками, сервер без консоли

Inno Setup копирует файлы и запускает установку компонентов **скрыто** (сообщение на
экране прогресса). Ярлыки запускают `run.vbs`: сервер стартует без чёрного окна, браузер
открывается сам. Журнал: `lexlock.log` рядом с приложением.

```cmd
iscc packaging\windows\installer.iss
```

Быстрый путь без сборки (из исходников):

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\install.ps1
```

## OCR

`install.sh`/`install.ps1` ставят Tesseract с русским языком и Python-extra `[ocr]`
(PyMuPDF). Отключить: `./install.sh --no-ocr`.

## Подпись файлов (code signing)

Шаги подписи в `.github/workflows/release.yml` запускаются, только если заданы секреты.

**macOS:** `APPLE_CERT_P12` (base64 .p12), `APPLE_CERT_PASSWORD`, `APPLE_ID`,
`APPLE_TEAM_ID`, `APPLE_APP_PASSWORD`. Нужен сертификат «Developer ID Application».

**Windows:** `WINDOWS_CERT_PFX_BASE64`, `WINDOWS_CERT_PASSWORD`. Нужен code-signing
сертификат. Без подписи Gatekeeper/SmartScreen показывают предупреждение — это ожидаемо.

## Релиз

Пуш тега `v*` запускает `release.yml`: собирает все три файла и прикладывает к GitHub
Release. **Не** кладите сборочные инструменты в `dist/` — они попадут в ассеты.

## Чего ещё нет

- Полностью офлайн-установка (модель и Ollama всё ещё докачиваются при первом запуске).
- Нотаризация macOS завязана на `.pkg`/`.app`; сейчас подписывается `.dmg` и вложенный `.app`.
