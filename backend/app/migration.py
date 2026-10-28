"""Преобразование проектов старого формата (несколько ячеек) в один файл кода.

Оригинал не теряется: он целиком вложен в поле original нового проекта, а при
открытии файла из папки проектов копируется в _originals/ (см. projects.py).
Старые снимки результатов к схеме по значениям и связям не привести, поэтому
запуск (run) у преобразованного проекта пустой — код нужно запустить заново.
"""
import copy


def is_legacy(data: dict) -> bool:
    return data.get("schemaVersion") == 1 or ("cells" in data and "code" not in data)


def cells_to_code(cells: list[dict]) -> str:
    """Склеивает ячейки в прежнем порядке; название ячейки — комментарием над ней."""
    parts = []
    for cell in cells:
        code = str(cell.get("code", "")).rstrip("\n")
        title = str(cell.get("title", "")).strip()
        if title:
            code = f"# {title}\n{code}" if code else f"# {title}"
        if code:
            parts.append(code)
    return "\n\n".join(parts) + "\n" if parts else ""


def migrate_v1(data: dict) -> dict:
    return {
        "schemaVersion": 2,
        "id": data.get("id", ""),
        "name": data.get("name") or "Без названия",
        "code": cells_to_code(data.get("cells", [])),
        "run": None,
        "createdAt": data.get("createdAt", ""),
        "updatedAt": data.get("updatedAt", ""),
        "migratedFrom": 1,
        "original": copy.deepcopy(data),
    }
