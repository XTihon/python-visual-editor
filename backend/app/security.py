"""Защита локального API от чужих веб-страниц.

Сервер слушает только 127.0.0.1, но браузер на этом же ПК может открыть любую
страницу, а она — отправить запрос на http://127.0.0.1:порт. Поэтому:
- Host должен быть 127.0.0.1 или localhost (защита от DNS rebinding);
- заголовок Origin, если он есть, должен принадлежать самому приложению;
- запросы, меняющие состояние (POST/PUT/DELETE), обязаны нести допустимый Origin —
  браузер подставляет его автоматически, и страница-злоумышленник его не подделает.
"""
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ALLOWED_HOSTNAMES = {"127.0.0.1", "localhost"}


def allowed_origins(port: int, dev: bool, dev_port: int) -> set[str]:
    ports = {port} | ({dev_port} if dev else set())
    return {f"http://{host}:{p}" for host in ALLOWED_HOSTNAMES for p in ports}


def _hostname(host_header: str) -> str:
    return urlsplit(f"//{host_header}").hostname or ""


def make_guard(origins: set[str]):
    async def guard(request: Request, call_next):
        if request.url.path.startswith("/api"):
            if _hostname(request.headers.get("host", "")) not in ALLOWED_HOSTNAMES:
                return JSONResponse({"detail": "Недопустимый Host."}, status_code=403)
            origin = request.headers.get("origin")
            if origin is not None and origin not in origins:
                return JSONResponse({"detail": "Недопустимый источник запроса (Origin)."}, status_code=403)
            if request.method not in SAFE_METHODS and origin is None:
                return JSONResponse({"detail": "Запрос без заголовка Origin отклонён."}, status_code=403)
        return await call_next(request)

    return guard
