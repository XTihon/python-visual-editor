"""Экспорт проекта: обычный .py-файл и Markdown-отчёт для разбора."""
from collections import Counter

from app.schemas import Project


def to_python(project: Project) -> str:
    return project.code if project.code.endswith("\n") or not project.code else project.code + "\n"


def _fence(text: str, lang: str = "") -> str:
    ticks = "```"
    while ticks in text:
        ticks += "`"
    return f"{ticks}{lang}\n{text.rstrip(chr(10))}\n{ticks}"


def _preview_text(value: dict) -> str:
    preview = value.get("preview")
    if not preview:
        return ""
    data = preview["data"]
    body = "\n".join("  ".join(row) for row in data) if data and isinstance(data[0], list) else "  ".join(data)
    if preview.get("hidden"):
        body += f"\n… скрыто элементов: {preview['hidden']}"
    return body


def _lines_text(lines) -> str:
    return ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in lines) if lines else ""


def to_markdown(project: Project) -> str:
    out = [f"# {project.name}", "", "## Код", "", _fence(project.code, "python"), ""]
    run = project.run
    if run is None:
        out += ["## Результат", "", "Программа ещё не запускалась.", ""]
    else:
        out += ["## Результат запуска", ""]
        status = "ошибка" if run.get("status") == "error" else "выполнено"
        out.append(f"Статус: **{status}**, {run.get('durationMs', 0)} мс.")
        if run.get("code") != project.code:
            out.append("")
            out.append("⚠ **Результат устарел:** код изменён после этого запуска.")
        if run.get("partial"):
            out += ["", "_Выполнение было прервано; показано только то, что успело выполниться._"]
        out.append("")

        graph = run.get("graph") or {}
        nodes = graph.get("nodes", [])
        values = [n for n in nodes if n.get("type") == "value"]
        counts = Counter(n["name"] for n in values)
        label = {n["id"]: n["name"] + (f" (v{n['version']})" if counts[n["name"]] > 1 else "") for n in values}
        label["output"] = "output"

        if values:
            out += ["### Значения", "", "| Имя | Тип | shape | dtype | Строка | Значение |", "|---|---|---|---|---|---|"]
            for n in values:
                v = n.get("value", {})
                shape = "×".join(map(str, v["shape"])) if v.get("shape") is not None else ""
                text = str(v.get("repr", "")).replace("|", "\\|").replace("\n", " ")
                text = text if len(text) <= 80 else text[:79] + "…"
                tag = " (изменён на месте)" if n.get("mutated") else ""
                out.append(f"| `{label[n['id']]}`{tag} | {v.get('type', '')} | {shape} | {v.get('dtype', '')} "
                           f"| {_lines_text(n.get('lines'))} | `{text}` |")
            out.append("")
            for n in values:
                body = _preview_text(n.get("value", {}))
                if body:
                    out += [f"`{label[n['id']]}`:", "", _fence(body), ""]
        edges = graph.get("edges", [])
        if edges:
            out += ["### Связи (откуда данные → куда)", ""]
            out += [f"- `{label.get(e['source'], e['source'])}` → `{label.get(e['target'], e['target'])}`" for e in edges]
            out.append("")
        if run.get("stdout"):
            out += ["### Вывод программы", "", _fence(run["stdout"]), ""]
        if run.get("stderr"):
            out += ["### stderr", "", _fence(run["stderr"]), ""]
        if run.get("outputTruncated"):
            out += ["_Вывод был обрезан по лимиту._", ""]
        error = run.get("error")
        if error:
            where = f", строка {error['line']}" if error.get("line") else ""
            out += [f"### Ошибка{where}", "", f"**{error.get('type', '')}:** {error.get('message', '')}", "",
                    _fence(error.get("text", "")), ""]
        if graph.get("notes") or graph.get("dropped"):
            out += ["### Ограничения анализа", ""]
            out += [f"- {note}" for note in graph.get("notes", [])]
            if graph.get("dropped"):
                out.append(f"- схема усечена: не показано значений — {graph['dropped']}")
            out.append("")

    original = project.original
    if original and original.get("cells"):
        out += ["## Исходные ячейки (старый формат)", "",
                "Проект был преобразован из ячеек в один файл. Заметки из оригинала:", ""]
        for i, cell in enumerate(original["cells"], 1):
            title = f" — {cell['title']}" if cell.get("title") else ""
            out.append(f"**Ячейка {i}{title}**")
            if cell.get("expected"):
                out.append(f"- Ожидание: {cell['expected']}")
            if cell.get("reflection"):
                out.append(f"- Итог: {cell['reflection']}")
            out.append("")
    return "\n".join(out).rstrip("\n") + "\n"
