import threading
import time

from tests.conftest import by_name


def wait_running(api):
    for _ in range(80):
        if api.get("/api/status").json()["running"]:
            return True
        time.sleep(0.1)
    return False


def test_infinite_loop_times_out_keeps_partial_graph_and_next_run_works(api):
    t0 = time.monotonic()
    run = api.run("a = 5\nb = a + 1\nwhile True:\n    pass\nnever = 1", timeout=1)
    assert time.monotonic() - t0 < 10
    assert run["status"] == "error" and run["partial"] is True
    assert run["error"]["kind"] == "timeout" and run["error"]["line"] == 3
    assert "(1 с)" in run["error"]["message"]
    assert set(by_name(run)) == {"a", "b"}  # то, что успело выполниться, не потеряно
    assert api.run("print(1 + 1)")["stdout"] == "2\n"


def test_stop_kills_running_program_and_app_stays_usable(api):
    holder = {}
    thread = threading.Thread(target=lambda: holder.update(run=api.run("x = 1\nwhile True:\n    pass", timeout=60)))
    thread.start()
    assert wait_running(api)
    time.sleep(0.5)  # дать дойти до цикла
    assert api.post("/api/stop").json() == {"stopped": True}
    thread.join(timeout=15)
    assert not thread.is_alive()
    run = holder["run"]
    assert run["error"]["kind"] == "stopped" and run["error"]["line"] == 2
    assert set(by_name(run)) == {"x"}
    assert api.run("print('ок')")["stdout"] == "ок\n"
    assert api.post("/api/stop").json() == {"stopped": False}


def test_only_one_run_at_a_time(api):
    thread = threading.Thread(target=lambda: api.run("import time\ntime.sleep(2)", timeout=10))
    thread.start()
    assert wait_running(api)
    resp = api.post("/api/run", json={"code": "1", "timeoutSec": 5})
    assert resp.status_code == 409
    thread.join(timeout=15)


def test_print_flood_is_truncated(api):
    run = api.run("for i in range(300000):\n    print('x' * 100)", timeout=60)
    assert run["status"] == "done" and run["outputTruncated"] is True
    assert len(run["stdout"]) <= 100_000


def test_user_code_cannot_break_protocol(api):
    run = api.run("import os, sys\nos.write(1, b'raw')\nsys.__stdout__.write('x')\nprint('ok')")
    assert run["stdout"] == "ok\n"
    assert api.run("input('?')")["error"]["type"] == "EOFError"
    assert api.run("import sys\nsys.exit(3)")["error"]["type"] == "SystemExit"
    assert api.run("print('alive')")["stdout"] == "alive\n"


def test_worker_crash_is_reported(api):
    run = api.run("a = 1\nimport os\nos._exit(7)")
    assert run["error"]["kind"] == "crash" and run["error"]["line"] == 3
    assert set(by_name(run)) == {"a"}
    assert api.run("print(1)")["stdout"] == "1\n"


def test_stderr_and_warnings_are_captured(api):
    run = api.run("import warnings, sys\nwarnings.warn('осторожно')\nprint('e', file=sys.stderr)")
    assert "осторожно" in run["stderr"] and run["stdout"] == ""


def test_runtime_error_text_hides_internals(api):
    run = api.run("def f(x):\n    return 1 / x\nf(0)")
    err = run["error"]
    assert err["line"] == 2 and err["type"] == "ZeroDivisionError"  # строка, где реально упало
    assert "worker.py" not in err["text"] and "tracer.py" not in err["text"]
    assert "return 1 / x" in err["text"]  # исходные строки в traceback


def test_lone_surrogate_in_value_does_not_crash_worker(api):
    run = api.run("s = '\\ud800'\nx = 1")
    assert run["status"] == "done", run["error"]
    assert set(by_name(run)) == {"s", "x"}
    assert "\ud800" not in str(run)  # серверу не должны приходить суррогаты
    assert api.run("print('жив')")["stdout"] == "жив\n"


def test_lone_surrogate_in_print_does_not_crash_worker(api):
    run = api.run("print('\\ud800')\nx = 1")
    assert run["status"] == "done", run["error"]
    assert set(by_name(run)) == {"x"}
    assert "\ud800" not in str(run)
    assert api.run("print('жив')")["stdout"] == "жив\n"


def test_lone_surrogate_in_error_text_does_not_crash_worker(api):
    run = api.run("raise ValueError('\\ud800')")
    assert run["error"]["type"] == "ValueError"
    assert "\ud800" not in str(run)
    assert api.run("print(1)")["stdout"] == "1\n"


def test_code_with_lone_surrogate_is_not_a_server_error(api):
    # браузер присылает суррогат экранированным в JSON, httpx.json= его бы не закодировал
    body = r'{"code": "s = \"\ud800\"\nx = 1", "timeoutSec": 10}'
    resp = api.client.post("/api/run", content=body,
                           headers={"Origin": "http://127.0.0.1:8742", "Content-Type": "application/json"})
    assert resp.status_code in (200, 400), resp.text
    assert api.run("print('жив')")["stdout"] == "жив\n"
