import pytest
from fastapi.testclient import TestClient

from app.main import create_app

PORT = 8742
ORIGIN = f"http://127.0.0.1:{PORT}"


class Api:
    """Тонкая обёртка над TestClient с правильными Host/Origin."""

    def __init__(self, client):
        self.client = client

    def run(self, code, timeout=20):
        resp = self.client.post("/api/run", json={"code": code, "timeoutSec": timeout}, headers={"Origin": ORIGIN})
        assert resp.status_code == 200, resp.text
        return resp.json()

    def post(self, url, **kwargs):
        return self.client.post(url, headers={"Origin": ORIGIN}, **kwargs)

    def put(self, url, **kwargs):
        return self.client.put(url, headers={"Origin": ORIGIN}, **kwargs)

    def get(self, url, **kwargs):
        return self.client.get(url, **kwargs)


@pytest.fixture(scope="session")
def projects_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("projects")


@pytest.fixture(scope="session")
def api(projects_dir):
    app = create_app(projects_dir=projects_dir, port=PORT, dev=False)
    with TestClient(app, base_url=ORIGIN) as client:
        yield Api(client)


def nodes(result, kind="value"):
    return [n for n in result["graph"]["nodes"] if n["type"] == kind]


def by_name(result):
    """имя → список версий узла по порядку."""
    out = {}
    for n in nodes(result):
        out.setdefault(n["name"], []).append(n)
    return out


def label(node):
    return node["name"] if node["type"] == "output" else f"{node['name']}#{node['version']}"


def edges(result):
    """Множество рёбер в читаемом виде: ('a#1', 'mask#1')."""
    names = {n["id"]: label(n) for n in result["graph"]["nodes"]}
    return {(names[e["source"]], names[e["target"]]) for e in result["graph"]["edges"]}
