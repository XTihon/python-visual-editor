"""FastAPI-приложение: API выполнения кода, проектов, экспорта и раздача интерфейса."""
import json
import logging
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.exports import to_markdown, to_python
from app.projects import InvalidProjectId, ProjectNotFound, ProjectStore, normalize
from app.schemas import Project, RunRequest
from app.security import allowed_origins, make_guard
from app.sessions import RunBusy, Runner, WorkerStartError

log = logging.getLogger("vizual")
EXAMPLE_ID = re.compile(r"^[a-z0-9-]{1,40}$")


def create_app(projects_dir: Path | None = None, port: int | None = None, dev: bool | None = None) -> FastAPI:
    port = port or config.PORT
    dev = config.DEV_MODE if dev is None else dev
    store = ProjectStore(projects_dir or config.PROJECTS_DIR)
    runner = Runner()

    @asynccontextmanager
    async def lifespan(_app):
        try:
            runner.prewarm()  # прогреваем: первый запуск ячейки не ждёт импорта NumPy
        except WorkerStartError:
            log.exception("Не удалось заранее запустить рабочий процесс")
        yield
        runner.shutdown()

    app = FastAPI(title="Визуальный редактор", lifespan=lifespan)
    app.state.runner = runner

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, exc: RequestValidationError):
        # Стандартный ответ повторяет введённые данные (input); одиночный суррогат в них не кодируется в UTF-8 → 500.
        errors = [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=400)
    app.middleware("http")(make_guard(allowed_origins(port, dev, config.DEV_PORT)))

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > config.MAX_BODY_BYTES:
            return JSONResponse({"detail": "Слишком большой запрос."}, status_code=413)
        return await call_next(request)

    # ---- выполнение -------------------------------------------------------

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/status")
    def get_status():
        return {**runner.status(), "defaultTimeoutSec": config.DEFAULT_TIMEOUT_SEC}

    @app.post("/api/stop")
    def stop():
        return {"stopped": runner.stop()}

    @app.post("/api/run")
    def run(req: RunRequest):
        try:
            return runner.run(req.code, min(req.timeoutSec, config.MAX_TIMEOUT_SEC))
        except RunBusy:
            raise HTTPException(409, "Программа уже выполняется. Дождитесь окончания или остановите её.")
        except WorkerStartError as exc:
            raise HTTPException(500, str(exc))

    # ---- проекты ----------------------------------------------------------

    @app.get("/api/projects")
    def list_projects():
        return store.list()

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str):
        try:
            return store.load(project_id)
        except InvalidProjectId as exc:
            raise HTTPException(400, str(exc))
        except ProjectNotFound:
            raise HTTPException(404, "Проект не найден.")

    @app.put("/api/projects/{project_id}")
    def save_project(project_id: str, project: Project):
        if project.id != project_id:
            raise HTTPException(400, "Идентификатор в адресе и в проекте не совпадает.")
        try:
            return store.save(project)
        except InvalidProjectId as exc:
            raise HTTPException(400, str(exc))
        except OSError as exc:
            raise HTTPException(500, f"Не удалось записать файл проекта: {exc}")

    @app.post("/api/projects/import")
    def import_project(payload: dict):
        """Принимает JSON проекта любого формата, возвращает проект текущего формата (не сохраняя)."""
        if not isinstance(payload, dict) or not ("code" in payload or "cells" in payload):
            raise HTTPException(400, "Это не файл проекта: нет поля «code» (или «cells» для старого формата).")
        data = normalize(payload)
        data["id"] = f"proj-{uuid.uuid4().hex[:10]}"  # импорт никогда не перезаписывает существующий проект
        data["createdAt"] = data["updatedAt"] = ""
        try:
            return Project.model_validate(data).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(400, f"Файл проекта повреждён: {exc}")

    # ---- экспорт ----------------------------------------------------------

    @app.post("/api/export/py")
    def export_py(project: Project):
        return PlainTextResponse(to_python(project), media_type="text/plain; charset=utf-8")

    @app.post("/api/export/md")
    def export_md(project: Project):
        text = to_markdown(project)
        return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")

    # ---- примеры ----------------------------------------------------------

    @app.get("/api/examples")
    def list_examples():
        items = []
        for path in sorted(config.EXAMPLES_DIR.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            items.append({"id": path.stem, "name": data["name"]})
        return items

    @app.get("/api/examples/{example_id}")
    def get_example(example_id: str):
        path = config.EXAMPLES_DIR / f"{example_id}.json"
        if not EXAMPLE_ID.fullmatch(example_id) or not path.is_file():
            raise HTTPException(404, "Пример не найден.")
        data = json.loads(path.read_text(encoding="utf-8"))
        # Копия под новым идентификатором: пример в папке приложения не перезаписывается.
        data["id"] = f"proj-{uuid.uuid4().hex[:10]}"
        return data

    # ---- интерфейс --------------------------------------------------------

    if config.FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")
    else:
        @app.get("/")
        def not_built():
            return PlainTextResponse(
                "Интерфейс не собран. Выполните .\\setup.ps1 (или в папке frontend: npm run build).",
                status_code=503,
            )

    return app


app = create_app()
