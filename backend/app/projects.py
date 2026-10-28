"""Хранение проектов в JSON-файлах внутри выделенной папки."""
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.migration import is_legacy, migrate_v1
from app.schemas import ID_PATTERN, Project


class ProjectNotFound(Exception):
    pass


class InvalidProjectId(ValueError):
    pass


def normalize(data: dict, fallback_id: str = "") -> dict:
    """Приводит словарь проекта любого поддерживаемого формата к текущему."""
    if is_legacy(data):
        data = migrate_v1(data)
        data["id"] = data["id"] or fallback_id
    return data


class ProjectStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.originals = self.directory / "_originals"

    def _path(self, project_id: str) -> Path:
        if not ID_PATTERN.fullmatch(project_id):
            raise InvalidProjectId("Недопустимый идентификатор проекта.")
        path = (self.directory / f"{project_id}.json").resolve()
        # Вторая линия защиты: итоговый путь обязан лежать в папке проектов.
        if path.parent != self.directory:
            raise InvalidProjectId("Недопустимый идентификатор проекта.")
        return path

    def list(self):
        items = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                items.append({
                    "id": data["id"],
                    "name": data.get("name", path.stem),
                    "updatedAt": data.get("updatedAt", ""),
                })
            except (OSError, ValueError, KeyError):
                continue  # битый файл не должен ломать список остальных
        items.sort(key=lambda item: item["updatedAt"], reverse=True)
        return items

    def load(self, project_id: str) -> dict:
        path = self._path(project_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ProjectNotFound(project_id)
        if is_legacy(data):
            self._backup_original(path, project_id)
        return normalize(data, project_id)

    def _backup_original(self, path: Path, project_id: str):
        """Файл старого формата копируется один раз и дальше не трогается."""
        self.originals.mkdir(exist_ok=True)
        backup = self.originals / f"{project_id}.v1.json"
        if not backup.exists():
            shutil.copy2(path, backup)

    def save(self, project: Project) -> dict:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        data = project.model_dump(mode="json")
        data["updatedAt"] = now
        data["createdAt"] = data["createdAt"] or now
        path = self._path(project.id)
        if path.exists():
            try:
                if is_legacy(json.loads(path.read_text(encoding="utf-8"))):
                    self._backup_original(path, project.id)  # перед первой перезаписью старого файла
            except (OSError, ValueError):
                pass
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)  # атомарно: недописанный файл не подменит рабочий
        return data
