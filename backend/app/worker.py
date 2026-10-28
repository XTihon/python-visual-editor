"""Рабочий процесс: выполняет одну программу пользователя.

Запускается как `python -m app.worker` отдельным процессом. Общение с сервером —
JSON-строки через stdin/stdout. Канал протокола — дубликаты дескрипторов 0 и 1,
а настоящие stdin/stdout перенаправлены в никуда, чтобы print()/input() из
пользовательского кода не портили протокол.

Сообщения воркера: ready, затем на каждый запуск — begin/step по инструкциям
и итоговое done. Если процесс убит по тайм-ауту, сервер уже получил всё,
что успело выполниться.

ВНИМАНИЕ: это не песочница. Код выполняется с правами текущего пользователя.
"""
import builtins
import contextlib
import io
import json
import linecache
import os
import sys
import time
import traceback

from app.config import BACKEND_DIR, OUTPUT_LIMIT_CHARS, WORKSPACE_DIR
from app.tracer import run_program

WORKER_FILE = os.path.abspath(__file__)
TRACER_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "tracer.py"))
INTERNAL_FILES = {WORKER_FILE, TRACER_FILE}


class LimitedStream(io.TextIOBase):
    """Текстовый поток с потолком по объёму: лишнее молча отбрасывается."""

    def __init__(self, limit):
        self._limit = limit
        self._parts = []
        self.size = 0
        self.truncated = False

    @property
    def encoding(self):
        return "utf-8"

    def writable(self):
        return True

    def write(self, text):
        if not isinstance(text, str):
            raise TypeError(f"write() argument must be str, not {type(text).__name__}")
        n = len(text)
        remaining = self._limit - self.size
        if remaining <= 0:
            self.truncated = True
            return n
        if n > remaining:
            text = text[:remaining]
            self.truncated = True
        self._parts.append(text)
        self.size += len(text)
        return n

    def flush(self):
        pass

    def getvalue(self):
        return "".join(self._parts)


def _open_channels():
    """Забирает stdin/stdout под протокол и отвязывает от них пользовательский код."""
    proto_in = os.fdopen(os.dup(0), "r", encoding="utf-8", newline="\n")
    # errors="replace": одиночный суррогат (например, '\ud800') не кодируется в UTF-8 и ронял бы процесс;
    # заменённый на "?" он доходит до сервера уже корректной строкой.
    proto_out = os.fdopen(os.dup(1), "w", encoding="utf-8", errors="replace", newline="\n")
    null_fd = os.open(os.devnull, os.O_RDWR)
    os.dup2(null_fd, 0)
    os.dup2(null_fd, 1)
    os.close(null_fd)
    sys.stdin = open(os.devnull, "r", encoding="utf-8")
    return proto_in, proto_out


def _send(proto_out, message):
    proto_out.write(json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n")
    proto_out.flush()


def _build_error(exc, filename):
    tb = exc.__traceback__
    # Срезаем кадры самого воркера: пользователь должен видеть только свой код.
    while tb is not None and os.path.abspath(tb.tb_frame.f_code.co_filename) in INTERNAL_FILES:
        tb = tb.tb_next
    text = "".join(traceback.TracebackException(type(exc), exc, tb).format())
    line = None
    cursor = tb
    while cursor is not None:
        if cursor.tb_frame.f_code.co_filename == filename:
            line = cursor.tb_lineno
        cursor = cursor.tb_next
    if isinstance(exc, SyntaxError):
        if exc.filename == filename and exc.lineno:
            line = exc.lineno
        message = exc.msg
    else:
        message = str(exc)
    return {
        "kind": "syntax" if isinstance(exc, SyntaxError) else "exception",
        "type": type(exc).__name__,
        "message": message,
        "text": text.rstrip("\n"),
        "line": line,
    }


def run(message, send):
    filename = message["filename"]
    code = message["code"]
    out = LimitedStream(OUTPUT_LIMIT_CHARS)
    err = LimitedStream(OUTPUT_LIMIT_CHARS)
    # Каждый запуск — чистое пространство имён, как при запуске файла.
    namespace = {"__name__": "__main__", "__builtins__": builtins, "__doc__": None, "__file__": filename}
    # Регистрируем исходник, чтобы traceback показывал строки кода.
    linecache.cache[filename] = (len(code), None, code.splitlines(True), filename)
    started = time.perf_counter()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            error = run_program(code, filename, namespace, send, out, lambda exc: _build_error(exc, filename))
        except BaseException as exc:  # SyntaxError до выполнения первой инструкции
            error = _build_error(exc, filename)
    return {
        "op": "done",
        "status": "error" if error else "done",
        "stdout": out.getvalue(),
        "stderr": err.getvalue(),
        "outputTruncated": out.truncated or err.truncated,
        "error": error,
        "durationMs": int((time.perf_counter() - started) * 1000),
    }


def main():
    proto_in, proto_out = _open_channels()
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(WORKSPACE_DIR)
    # Внутренние модули не должны быть доступны пользователю через import.
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") not in (str(BACKEND_DIR), os.path.abspath("."))]
    sys.path.insert(0, str(WORKSPACE_DIR))

    def send(message):
        _send(proto_out, message)

    send({"op": "ready", "pid": os.getpid()})
    for raw in proto_in:
        message = json.loads(raw)
        if message["op"] == "exit":
            break
        if message["op"] == "run":
            send(run(message, send))


if __name__ == "__main__":
    main()
