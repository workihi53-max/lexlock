"""Веб-слой «Вани» (Legal AI Vault): FastAPI + одиночная статическая страница.

Слой общается с ядром vanya только через замороженные интерфейсы из SPEC.md §2.1–2.8.
Ollama не обязательна: детерминированные сценарии работают без модели.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from vanya import agent as vanya_agent
from vanya import config as vanya_config
from vanya import llm as vanya_llm
from vanya import offline as vanya_offline
from vanya import scenarios as vanya_scenarios

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# Максимальный размер одного загружаемого файла (защита от забивания диска).
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


# --- модели запросов (pydantic v2) -------------------------------------------

class FillRequest(BaseModel):
    filename: str | None = None  # пустое/отсутствует → режим «пакет» (все документы)
    out_name: str | None = None


class RisksRequest(BaseModel):
    filename: str


class AskRequest(BaseModel):
    filename: str
    question: str


class ChecklistRequest(BaseModel):
    filename: str
    contract_type: str | None = None


class ChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None


# --- проверка имён файлов -----------------------------------------------------

def safe_workspace_path(workspace: Path, name: str) -> Path:
    """Только голое имя файла внутри workspace, без '..', путей и симлинков."""
    if not name or name in (".", ".."):
        raise ValueError("недопустимое имя файла")
    if "/" in name or "\\" in name or Path(name).name != name:
        raise ValueError("имя файла не должно содержать путь")
    path = workspace / name
    if path.is_symlink():
        raise ValueError("символьные ссылки запрещены")
    if not path.resolve().is_relative_to(workspace.resolve()):
        raise ValueError("файл находится вне рабочей папки")
    return path


def _checked_path(workspace: Path, name: str) -> Path:
    try:
        return safe_workspace_path(workspace, name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _scenario_error(detail: str) -> HTTPException:
    return HTTPException(status_code=500, detail=f"ошибка сценария: {detail}")


def _sse_line(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _event_parts(event: Any) -> tuple[str, dict]:
    """Event из vanya (kind/data) либо такой же dict."""
    if isinstance(event, dict):
        return event.get("kind", "status"), event.get("data", {})
    return event.kind, event.data


# --- приложение ---------------------------------------------------------------

def create_app(config: Any | None = None) -> FastAPI:
    config = config if config is not None else vanya_config.load_config()
    workspace = Path(config.workspace)
    llm = vanya_llm.LLM(config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        workspace.mkdir(parents=True, exist_ok=True)
        if config.offline:
            vanya_offline.enforce_offline()
        mode = "офлайн" if config.offline else "отладка"
        print(f"Ваня запущен — адрес: http://127.0.0.1:{config.port} "
              f"| модель: {config.model} | режим: {mode}")
        yield

    app = FastAPI(title="Ваня — локальный юридический ИИ", lifespan=lifespan)

    # --- статика ---------------------------------------------------------------

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    # --- health ----------------------------------------------------------------

    @app.get("/api/health")
    def health():
        try:
            h = llm.health()
        except Exception:  # Ollama недоступна — приложение всё равно работает
            h = {"ok": False, "installed": False, "error": "Ollama недоступна"}
        return {
            "ok": True,
            "model": h.get("model", config.model),
            "model_installed": bool(h.get("installed", False)),
            "offline": bool(config.offline),
            "ollama": bool(h.get("ok", False)),
            "workspace": str(workspace),
        }

    # --- файлы -----------------------------------------------------------------

    @app.get("/api/files")
    def list_files():
        files = []
        for path in sorted(workspace.iterdir()):
            if path.is_file() and not path.is_symlink():
                files.append({"name": path.name, "size": path.stat().st_size,
                              "ext": path.suffix})
        return {"files": files}

    @app.post("/api/upload")
    async def upload(files: list[UploadFile] = File(...)):
        if not files:
            raise HTTPException(status_code=400, detail="файлы не переданы")
        pending: list[tuple[Path, str, bytes]] = []
        for item in files:
            raw = (item.filename or "").replace("\\", "/")
            name = raw.rsplit("/", 1)[-1]
            try:
                dest = safe_workspace_path(workspace, name)
            except ValueError:
                continue  # битые имена пропускаем, о корректных сообщаем
            data = await item.read()
            if len(data) > MAX_UPLOAD_BYTES:
                limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
                raise HTTPException(
                    status_code=413,
                    detail=f"файл «{name}» больше {limit_mb} МБ",
                )
            pending.append((dest, name, data))
        if not pending:
            raise HTTPException(status_code=400,
                                detail="ни один файл не сохранён: некорректные имена")
        saved: list[str] = []
        for dest, name, data in pending:
            dest.write_bytes(data)
            saved.append(name)
        return {"saved": saved}

    @app.get("/api/download/{name}")
    def download(name: str):
        path = _checked_path(workspace, name)
        if not path.is_file():
            raise HTTPException(status_code=404,
                                detail=f"файл «{name}» не найден")
        return FileResponse(path, filename=path.name)

    # --- сценарии ----------------------------------------------------------------

    @app.post("/api/scenario/fill")
    def scenario_fill(req: FillRequest):
        # пустой filename — легальный режим «пакет»: ядро берёт все документы
        if req.filename:
            _checked_path(workspace, req.filename)
        try:
            result = vanya_scenarios.fill_contract(req.filename or None, req.out_name)
        except Exception as exc:
            raise _scenario_error(str(exc)) from exc
        if not result.get("ok", True):
            raise HTTPException(status_code=400,
                                detail=result.get("error", "не удалось заполнить договор"))
        # удобное имя для ссылки на скачивание (см. NOTES.md)
        if "download_name" not in result and result.get("out_path"):
            result["download_name"] = Path(str(result["out_path"])).name
        return result

    @app.post("/api/scenario/risks")
    def scenario_risks(req: RisksRequest):
        _checked_path(workspace, req.filename)
        try:
            return vanya_scenarios.find_risks(req.filename)
        except Exception as exc:
            raise _scenario_error(str(exc)) from exc

    @app.post("/api/scenario/export_risks")
    def scenario_export_risks(req: RisksRequest):
        _checked_path(workspace, req.filename)
        try:
            return vanya_scenarios.export_risks(req.filename)
        except Exception as exc:
            raise _scenario_error(str(exc)) from exc

    @app.post("/api/scenario/ask")
    def scenario_ask(req: AskRequest):
        _checked_path(workspace, req.filename)
        if not req.question.strip():
            raise HTTPException(status_code=400, detail="вопрос пустой")
        try:
            return vanya_scenarios.ask(req.filename, req.question)
        except Exception as exc:
            raise _scenario_error(str(exc)) from exc

    @app.post("/api/scenario/checklist")
    def scenario_checklist(req: ChecklistRequest):
        _checked_path(workspace, req.filename)
        try:
            return vanya_scenarios.check_contract(req.filename, req.contract_type)
        except Exception as exc:
            raise _scenario_error(str(exc)) from exc

    # --- чат (SSE) ---------------------------------------------------------------

    async def _sse_events(message: str, history: list[dict] | None) -> AsyncIterator[str]:
        q: queue.Queue = queue.Queue()

        def run_agent() -> None:
            # работаем в потоке, чтобы uvicorn не блокировался генератором Agent.run
            try:
                agent = vanya_agent.Agent(llm=llm)
                for event in agent.run(message, history):
                    q.put(("event", event))
            except Exception as exc:  # SSE не должен падать: ошибку шлём как событие
                q.put(("error", str(exc)))
            q.put(("done", None))

        threading.Thread(target=run_agent, daemon=True).start()
        yield ": подключено\n\n"
        try:
            while True:
                kind, payload = await asyncio.to_thread(q.get)
                if kind == "done":
                    yield ": done\n\n"
                    return
                if kind == "error":
                    yield _sse_line({"kind": "error",
                                     "data": {"message": str(payload)}})
                    continue
                try:
                    ev_kind, ev_data = _event_parts(payload)
                    yield _sse_line({"kind": ev_kind, "data": ev_data})
                except TypeError:
                    yield _sse_line({"kind": "error",
                                     "data": {"message": "событие не сериализуется"}})
        except asyncio.CancelledError:  # клиент закрыл соединение
            return

    @app.post("/api/chat")
    async def chat(req: ChatRequest):
        if not req.message.strip():
            raise HTTPException(status_code=400, detail="сообщение пустое")
        return StreamingResponse(
            _sse_events(req.message, req.history),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()

if __name__ == "__main__":
    cfg = vanya_config.load_config()
    uvicorn.run(app, host="127.0.0.1", port=cfg.port)
