"""Константы и пути приложения."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

HOST = "127.0.0.1"
PORT = int(os.environ.get("VR_PORT", "8742"))
DEV_MODE = os.environ.get("VR_DEV") == "1"
DEV_PORT = 5173

DATA_DIR = Path(os.environ.get("VR_DATA_DIR", ROOT_DIR / "data"))
PROJECTS_DIR = DATA_DIR / "projects"
WORKSPACE_DIR = DATA_DIR / "workspace"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"

# Выполнение кода
DEFAULT_TIMEOUT_SEC = 30
MAX_TIMEOUT_SEC = 300
WORKER_START_TIMEOUT_SEC = 30
OUTPUT_LIMIT_CHARS = 100_000  # отдельно для stdout и stderr
MAX_GRAPH_NOTES = 6
MAX_CODE_CHARS = 200_000

# Проекты
MAX_BODY_BYTES = 20 * 1024 * 1024
MAX_RUN_BYTES = 6 * 1024 * 1024
