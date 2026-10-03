# Установщики «Вани»

Здесь лежат сборки для трёх систем. Все они используют один принцип: установщик
кладет проект, а при первом запуске `install.sh`/`install.ps1` сам ставит `uv`,
Ollama, зависимости и модель (нужен интернет один раз, дальше всё офлайн).

| Система | Файл | Сборка | Статус |
|---|---|---|---|
| macOS | `Vanya-<версия>.dmg` | `bash packaging/macos/build_dmg.sh` (только macOS) | проверено локально |
| Linux | `Vanya-<версия>-<арх>.AppImage` | `bash packaging/linux/build_appimage.sh` (Linux) | собирается в CI |
| Windows | `Vanya-<версия>-win-setup.exe` | `iscc packaging/windows/installer.iss` (Windows) | собирается в CI |

Автоматическая сборка всех трёх — по тегу `v*`: workflow `.github/workflows/release.yml`
соберёт файлы и приложит их к GitHub Release.

## macOS

```bash
bash packaging/macos/build_dmg.sh   # → dist/Vanya-0.1.0.dmg
```

Пользователь открывает `.dmg`, перетаскивает «Ваня» и запускает
«Установить и запустить.command» двойным кликом. Откроется Терминал, пройдёт
установка, браузер откроется сам.

## Linux (AppImage)

```bash
bash packaging/linux/build_appimage.sh   # → dist/Vanya-0.1.0-x86_64.AppImage
```

AppImage универсален: один файл для большинства дистрибутивов. При первом запуске
разворачивает проект в `~/vanya-legal-vault` и ставит компоненты.

```bash
chmod +x Vanya-0.1.0-x86_64.AppImage
./Vanya-0.1.0-x86_64.AppImage
```

## Windows

Быстрый путь без сборки — из архива с исходниками:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\install.ps1
run.bat
```

Полный установщик (ярлыки, автозапуск установки) собирается Inno Setup 6:

```cmd
iscc packaging\windows\installer.iss
```

## Чего ещё нет

- Установщики без интернета (модель и Ollama всё ещё скачиваются при первом запуске).
- Код-подпись `.dmg`/`.exe` — сейчас предупреждения Gatekeeper/SmartScreen ожидаемы.
- Единый бинарник с вшитым Python — сейчас Python ставит `uv` автоматически.
