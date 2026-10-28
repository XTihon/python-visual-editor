"""Запуск программы в отдельном рабочем процессе.

Каждый запуск — новый процесс с чистой памятью (как запуск файла). Чтобы не ждать
импорта NumPy, следующий процесс заранее готовится в фоне. Одновременно выполняется
только один запуск. Остановка и тайм-аут завершают процесс целиком (вместе с дочерними),
но всё, что успело выполниться, остаётся в результате.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

from app.config import BACKEND_DIR, MAX_GRAPH_NOTES, WORKER_START_TIMEOUT_SEC, WORKSPACE_DIR

FILENAME = "<программа>"


class RunBusy(Exception):
    """Попытка запустить код, пока выполняется другой запуск."""


class WorkerStartError(Exception):
    """Рабочий процесс не удалось запустить."""


class _Worker:
    def __init__(self):
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "app.worker"],
            cwd=BACKEND_DIR, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, encoding="utf-8", creationflags=flags,
        )
        self.lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        try:
            first = self.lines.get(timeout=WORKER_START_TIMEOUT_SEC)
        except queue.Empty:
            self.kill()
            raise WorkerStartError("Рабочий процесс не ответил при запуске.")
        if first is None or json.loads(first).get("op") != "ready":
            self.kill()
            raise WorkerStartError("Рабочий процесс завершился при запуске.")

    def _read(self):
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)  # конец потока: процесс завершился

    def alive(self):
        return self.proc.poll() is None

    def kill(self):
        if self.proc.poll() is not None:
            return
        if sys.platform == "win32":
            # /T — вместе с дочерними процессами пользовательского кода
            subprocess.run(
                ["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
            )
        try:
            self.proc.kill()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


class Runner:
    def __init__(self):
        self._state_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._spare_lock = threading.Lock()  # держится на время запуска запасного процесса
        self._spare: _Worker | None = None
        self._active: _Worker | None = None
        self._running = False
        self._cancel_reason = None

    # ---- процессы -----------------------------------------------------------

    def prewarm(self):
        with self._spare_lock:
            if self._spare is None or not self._spare.alive():
                self._spare = _Worker()

    def _take_worker(self) -> _Worker:
        with self._spare_lock:
            worker, self._spare = self._spare, None
            if worker is None or not worker.alive():
                worker = _Worker()
            return worker

    def _recycle(self, worker: _Worker):
        def job():
            worker.kill()
            try:
                self.prewarm()
            except WorkerStartError:
                pass

        threading.Thread(target=job, daemon=True).start()

    def shutdown(self):
        with self._state_lock:
            active = self._active
        if active:
            active.kill()
        with self._spare_lock:
            if self._spare:
                self._spare.kill()
                self._spare = None

    # ---- состояние и остановка -------------------------------------------------

    def status(self):
        with self._state_lock:
            return {"running": self._running}

    def stop(self) -> bool:
        with self._state_lock:
            if not self._running or self._active is None:
                return False
            self._cancel_reason = "stop"
            active = self._active
        active.kill()
        return True

    # ---- запуск -----------------------------------------------------------------

    def run(self, code: str, timeout_sec: int) -> dict:
        if not self._run_lock.acquire(blocking=False):
            raise RunBusy()
        worker = None
        try:
            worker = self._take_worker()
            with self._state_lock:
                self._active, self._running, self._cancel_reason = worker, True, None
            return self._run(worker, code, timeout_sec)
        finally:
            with self._state_lock:
                self._active, self._running = None, False
            if worker is not None:
                self._recycle(worker)
            self._run_lock.release()

    def _run(self, worker: _Worker, code: str, timeout_sec: int) -> dict:
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        t0 = time.monotonic()
        nodes: dict[str, dict] = {}  # id → узел, порядок вставки сохраняется
        edges: list[dict] = []
        notes: list[str] = []
        dropped = 0
        current_line = None
        done = None
        problem = None  # "timeout" | "stopped" | "crash"

        try:
            worker.proc.stdin.write(json.dumps({"op": "run", "filename": FILENAME, "code": code}, ensure_ascii=False) + "\n")
            worker.proc.stdin.flush()
        except (OSError, ValueError):
            problem = "crash"

        deadline = t0 + timeout_sec
        while problem is None and done is None:
            try:
                line = worker.lines.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                problem = "timeout"
                break
            if line is None:
                problem = "stopped" if self._cancel_reason == "stop" else "crash"
                break
            msg = json.loads(line)
            if msg["op"] == "begin":
                current_line = msg["line"]
            elif msg["op"] == "step":
                for node in msg["nodes"]:
                    nodes[node["id"]] = node
                edges.extend(msg["edges"])
                notes.extend(n for n in msg["notes"] if n not in notes)
                dropped = msg["dropped"]
            elif msg["op"] == "done":
                done = msg

        duration_ms = int((time.monotonic() - t0) * 1000)
        result = {
            "status": "done", "startedAt": started_at, "durationMs": duration_ms, "code": code,
            "stdout": "", "stderr": "", "outputTruncated": False, "error": None, "partial": False,
            "notice": None,
        }
        if done is not None:
            result.update({k: done[k] for k in ("status", "stdout", "stderr", "outputTruncated", "error", "durationMs")})
        else:
            worker.kill()
            result["status"] = "error"
            result["partial"] = True
            text = {
                "timeout": f"Превышен лимит времени ({timeout_sec} с): программа остановлена.",
                "stopped": "Программа остановлена.",
                "crash": "Рабочий процесс неожиданно завершился.",
            }[problem]
            result["error"] = {
                "kind": problem, "type": {"timeout": "TimeoutError", "stopped": "Stopped", "crash": "WorkerCrashed"}[problem],
                "message": text, "text": text, "line": current_line,
            }
            result["notice"] = "Показано только то, что успело выполниться до остановки."
            result["stdout"] = nodes["output"]["text"] if "output" in nodes else ""
        result["graph"] = {
            "nodes": list(nodes.values()), "edges": edges, "notes": notes[:MAX_GRAPH_NOTES], "dropped": dropped,
        }
        return result
