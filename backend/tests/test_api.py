import json
from pathlib import Path

import pytest

from app.config import EXAMPLES_DIR
from app.schemas import Project
from tests.conftest import ORIGIN, by_name, edges

FIXTURE = Path(__file__).parent / "fixtures" / "v1_project.json"  # реальный старый проект (ячейки переставлены)
ORDERED = Path(__file__).parent / "fixtures" / "v1_ordered.json"
SPEC = "import numpy as np\n\na = np.array([2, 7, 4, 9])\nmask = a > 5\nresult = a[mask]\nprint(result)\n"


def make_project(project_id="proj-test1", name="Тест", code="x = [1, 2]\nprint(x)\n", run=None):
    return {"schemaVersion": 2, "id": project_id, "name": name, "code": code, "run": run,
            "createdAt": "", "updatedAt": ""}


# ---- сохранение и повторное открытие ---------------------------------------------

def test_save_and_reopen_project_with_graph(api):
    run = api.run(SPEC)
    saved = api.put("/api/projects/proj-save", json=make_project("proj-save", "Сохранение", SPEC, run))
    assert saved.status_code == 200 and saved.json()["updatedAt"]
    loaded = api.get("/api/projects/proj-save").json()
    assert loaded["name"] == "Сохранение" and loaded["code"] == SPEC
    assert loaded["run"]["code"] == SPEC and loaded["run"]["stdout"] == "[7 9]\n"
    names = {n["name"]: n for n in loaded["run"]["graph"]["nodes"]}
    assert names["result"]["value"]["preview"]["data"] == ["7", "9"]
    assert loaded["run"]["graph"]["edges"] == run["graph"]["edges"]
    assert "Сохранение" in [p["name"] for p in api.get("/api/projects").json()]


@pytest.mark.parametrize("bad_id", ["..", "../x", "a/b", "a\\b", "C:evil", "con.", "x" * 65, "имя", "a b"])
def test_project_id_cannot_escape_folder(api, bad_id):
    resp = api.put(f"/api/projects/{bad_id}", json=make_project(bad_id))
    assert resp.status_code in (400, 404, 405, 422)
    assert api.get(f"/api/projects/{bad_id}").status_code in (400, 404, 405, 422)


def test_url_traversal_is_rejected(api):
    assert api.get("/api/projects/..%2F..%2Fsecret").status_code in (400, 404)
    assert api.get("/api/projects/%2e%2e").status_code in (400, 404)


def test_path_in_body_id_mismatch(api):
    assert api.put("/api/projects/proj-other", json=make_project("proj-test1")).status_code == 400


def test_missing_project_is_404(api):
    assert api.get("/api/projects/nope-123").status_code == 404


# ---- старые проекты --------------------------------------------------------------

def test_legacy_project_opens_as_continuous_code_in_original_order(api, projects_dir):
    legacy = json.loads(FIXTURE.read_text(encoding="utf-8"))
    (projects_dir / "proj-legacy1.json").write_text(json.dumps({**legacy, "id": "proj-legacy1"}), encoding="utf-8")
    opened = api.get("/api/projects/proj-legacy1").json()
    Project.model_validate(opened)
    assert opened["schemaVersion"] == 2 and opened["migratedFrom"] == 1 and opened["run"] is None
    codes = [c["code"].strip() for c in legacy["cells"] if c["code"].strip()]
    positions = [opened["code"].index(code) for code in codes]
    assert positions == sorted(positions) and len(set(positions)) == len(codes)  # порядок сохранён
    for cell in legacy["cells"]:
        if cell["title"]:
            assert f"# {cell['title']}" in opened["code"]
    assert "import numpy as np" in opened["code"]
    # оригинал сохранён целиком: внутри проекта и отдельным файлом
    assert opened["original"]["cells"] == legacy["cells"]
    backup = projects_dir / "_originals" / "proj-legacy1.v1.json"
    assert json.loads(backup.read_text(encoding="utf-8"))["cells"] == legacy["cells"]
    assert "proj-legacy1" in [p["id"] for p in api.get("/api/projects").json()]
    # старый файл на диске остаётся нетронутым до первого сохранения
    assert json.loads((projects_dir / "proj-legacy1.json").read_text(encoding="utf-8"))["schemaVersion"] == 1


def test_legacy_project_converted_code_runs_and_saves_as_new_format(api, projects_dir):
    legacy = json.loads(ORDERED.read_text(encoding="utf-8"))
    (projects_dir / "proj-legacy2.json").write_text(json.dumps({**legacy, "id": "proj-legacy2"}), encoding="utf-8")
    opened = api.get("/api/projects/proj-legacy2").json()
    run = api.run(opened["code"])
    assert run["status"] == "done"
    assert {"a", "mask", "result"} <= set(by_name(run))
    assert ("a#1", "mask#1") in edges(run) and run["stdout"] == "[7 9]\n"
    opened["run"] = run
    assert api.put("/api/projects/proj-legacy2", json=opened).status_code == 200
    again = api.get("/api/projects/proj-legacy2").json()
    assert again["schemaVersion"] == 2 and again["original"]["cells"] == legacy["cells"]
    assert (projects_dir / "_originals" / "proj-legacy2.v1.json").exists()


def test_import_endpoint_converts_legacy_and_assigns_new_id(api):
    legacy = json.loads(FIXTURE.read_text(encoding="utf-8"))
    imported = api.post("/api/projects/import", json=legacy).json()
    assert imported["id"] != legacy["id"] and imported["migratedFrom"] == 1 and imported["original"]["cells"]
    again = api.post("/api/projects/import", json=make_project("proj-keep", code="A = 1\n")).json()
    assert again["id"] != "proj-keep" and again["code"] == "A = 1\n" and again["migratedFrom"] is None
    assert api.post("/api/projects/import", json={"name": "x"}).status_code == 400


def test_legacy_notes_survive_in_markdown_report(api):
    legacy = json.loads(FIXTURE.read_text(encoding="utf-8"))
    project = api.post("/api/projects/import", json=legacy).json()
    md = api.post("/api/export/md", json=project).text
    assert "Исходные ячейки (старый формат)" in md and "Ожидание:" in md


# ---- экспорт ----------------------------------------------------------------------

def test_export_python_is_the_plain_code(api):
    py = api.post("/api/export/py", json=make_project(code=SPEC))
    assert py.text == SPEC
    compile(py.text, "exported.py", "exec")


def test_export_markdown_report(api):
    code = SPEC + "z = 1 / 0\n"
    run = api.run(code)
    md = api.post("/api/export/md", json=make_project(code=code, run=run)).text
    for fragment in ("# Тест", "## Код", "```python", "### Значения", "| `a` |", "`a` → `mask`", "`result` → `output`",
                     "[7 9]", "ZeroDivisionError", "Traceback"):
        assert fragment in md, fragment


def test_markdown_marks_stale_result(api):
    run = api.run("a = 1")
    md = api.post("/api/export/md", json=make_project(code="a = 2", run=run)).text
    assert "Результат устарел" in md


# ---- примеры ----------------------------------------------------------------------

def test_examples_are_valid_and_run_without_errors(api):
    ids = [e["id"] for e in api.get("/api/examples").json()]
    assert set(ids) == {"mask-selection", "reshape", "neuron"}
    for example_id in ids:
        data = api.get(f"/api/examples/{example_id}").json()
        Project.model_validate(data)
        run = api.run(data["code"])
        assert run["status"] == "done", (example_id, run["error"])
        assert run["graph"]["nodes"] and run["graph"]["edges"]


def test_neuron_example_has_real_values_and_links(api):
    run = api.run(api.get("/api/examples/neuron").json()["code"])
    v = by_name(run)
    assert v["weighted_sum"][0]["value"]["repr"] == "0.30000000000000004"
    assert v["output"][0]["value"]["repr"] == "2.3" and run["stdout"] == "2.3\n"
    assert ("products#1", "weighted_sum#1") in edges(run) and ("weighted_sum#1", "output#1") in edges(run)


def test_example_ids_are_validated(api):
    assert api.get("/api/examples/..%2F..%2Fconfig").status_code == 404


def test_examples_files_are_well_formed():
    for path in EXAMPLES_DIR.glob("*.json"):
        Project.model_validate(json.loads(path.read_text(encoding="utf-8")))


# ---- защита источника запросов -------------------------------------------------------

def test_post_without_origin_is_rejected(api):
    assert api.client.post("/api/stop").status_code == 403


@pytest.mark.parametrize("origin", ["http://evil.example", "http://127.0.0.1:9999", "null", "http://localhost:8742.evil.com"])
def test_foreign_origin_is_rejected(api, origin):
    resp = api.client.post("/api/run", json={"code": "print(1)", "timeoutSec": 5}, headers={"Origin": origin})
    assert resp.status_code == 403
    assert api.client.get("/api/projects", headers={"Origin": origin}).status_code == 403


def test_foreign_host_is_rejected_dns_rebinding(api):
    assert api.client.get("/api/projects", headers={"Host": "evil.example:8742"}).status_code == 403


def test_allowed_origins_work(api):
    for origin in (ORIGIN, "http://localhost:8742"):
        assert api.client.post("/api/stop", headers={"Origin": origin}).status_code == 200


def test_huge_body_is_rejected(api):
    resp = api.client.post("/api/export/py", content=b"x" * 10,
                           headers={"Origin": ORIGIN, "Content-Length": str(30 * 1024 * 1024)})
    assert resp.status_code in (413, 400, 422)
