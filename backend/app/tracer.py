"""Выполнение программы по инструкциям верхнего уровня и построение графа значений.

Для каждой инструкции:
1. разбор (analysis.py) говорит, какие имена она читает и записывает;
2. инструкция выполняется ОДИН раз обычным exec;
3. сравнивается состояние переменных до и после: записанные имена и имена, чьё
   содержимое изменилось на месте (в том числе через псевдоним), получают новую
   версию — узел с независимой копией значения;
4. связи идут от последних версий прочитанных имён к новым узлам.

Выражения для визуализации повторно не вычисляются: значения берутся только из
реального выполнения. Промежуточные значения внутри выражения (например, a > 5 в
a[a > 5]) в схему не попадают — только то, что программа сохранила в переменные.
"""
import ast
import contextlib
import hashlib
import io
import types

import numpy as np

from app.analysis import StmtInfo, analyze_statement
from app.snapshot import classify, describe, safe_repr

MAX_NODES = 80
MAX_EDGES = 300
MAX_NOTES = 6
PREVIEW_BUDGET_BYTES = 1_500_000
FULL_HASH_UNTOUCHED = 200_000  # элементов массива
FULL_HASH_TOUCHED = 5_000_000
SAMPLE_SIZE = 4096
HIDDEN_KINDS = {"module", "function", "class"}


def _array_key(arr: np.ndarray, full_limit: int):
    """(id, форма, dtype, хэш выборки, полный хэш или None) — для поиска изменений на месте."""
    size = arr.size
    if arr.dtype.kind == "O":
        sample = repr(arr.reshape(-1)[:200].tolist()) if size else ""
        return (id(arr), arr.shape, str(arr.dtype), hash(sample), None)
    step = max(1, size // SAMPLE_SIZE)
    sample = arr.flat[::step] if size else arr
    sample_hash = hashlib.blake2b(np.ascontiguousarray(sample).tobytes(), digest_size=8).hexdigest()
    full_hash = None
    if size <= full_limit:
        full_hash = hashlib.blake2b(np.ascontiguousarray(arr).tobytes(), digest_size=8).hexdigest()
    return (id(arr), arr.shape, str(arr.dtype), sample_hash, full_hash)


def state_key(value, full_limit: int):
    if isinstance(value, np.ndarray):
        return _array_key(value, full_limit)
    if isinstance(value, (list, tuple)):
        head = "|".join(safe_repr(x, 100) for x in value[:200])
        return (id(value), len(value), hash(head))
    if isinstance(value, dict):
        # значения — по id: d['a'] = 2 подменяет объект, а d['k'].append(1) — нет (вложенное не отслеживается)
        head = "|".join(f"{safe_repr(k, 100)}:{id(v)}" for k, v in list(value.items())[:100])
        return (id(value), len(value), hash(head))
    if isinstance(value, (set, frozenset)):
        items = list(value)[:100]
        head = "|".join(safe_repr(x, 100) for x in items)
        return (id(value), len(value), hash(head))
    if isinstance(value, str):
        return ("str", len(value), hash(value))
    if isinstance(value, (bool, int, float, complex, type(None), np.generic)):
        return (type(value).__name__, safe_repr(value, 200))
    return (id(value), type(value).__name__, safe_repr(value, 200))


def keys_differ(old, new) -> bool:
    if len(old) != len(new):
        return True
    if len(new) == 5:  # массив: (id, форма, dtype, хэш выборки, полный хэш или None)
        if old[:4] != new[:4]:
            return True
        return old[4] != new[4] if old[4] is not None and new[4] is not None else False
    return old != new


class Tracer:
    def __init__(self, namespace: dict, send):
        self.ns = namespace
        self.send = send
        self.keys: dict = {}
        self.latest: dict[str, str | None] = {}  # имя → id последнего узла (None — узел не создан из-за лимита)
        self.versions: dict[str, int] = {}
        self.infos: dict[str, dict] = {}  # id узла → описание значения
        self.user_callables: set[str] = set()
        self.seq = 0
        self.node_count = 0
        self.edge_count = 0
        self.dropped = 0
        self.dropped_sent = 0
        self.preview_budget = PREVIEW_BUDGET_BYTES
        self.edge_set: set[tuple[str, str]] = set()
        self.notes: list[str] = []
        self.output_lines: list[list[int]] = []
        self.output_sources: set[str] = set()

    # ---- заметки об ограничениях анализа ------------------------------------

    def _note(self, text: str, step_notes: list[str]):
        if text not in self.notes and len(self.notes) < MAX_NOTES:
            self.notes.append(text)
            step_notes.append(text)

    # ---- основной шаг ---------------------------------------------------------

    def after_statement(self, info: StmtInfo, failed: bool, printed: bool, output_text: str, output_truncated: bool):
        step_nodes: list[dict] = []
        step_edges: list[dict] = []
        step_notes: list[str] = []
        prev_latest = dict(self.latest)  # связи строим по состоянию ДО инструкции

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            changed = self._detect_changes(info, failed)
            for name, mutated in changed.items():
                node = self._make_node(name, mutated, info, prev_latest, step_edges, step_notes)
                if node:
                    step_nodes.append(node)

        if not info.supported and info.reason and (changed or printed):
            where = f"строка {info.start}" if info.start == info.end else f"строки {info.start}–{info.end}"
            self._note(f"{where}: {info.reason} — значения показаны, связи не определяются", step_notes)

        if printed:
            step_nodes.append(self._output_node(info, prev_latest, step_edges, output_text, output_truncated))

        if step_nodes or step_edges or step_notes or self.dropped != self.dropped_sent:
            self.dropped_sent = self.dropped
            self.send({"op": "step", "nodes": step_nodes, "edges": step_edges, "notes": step_notes,
                       "dropped": self.dropped})

    def _detect_changes(self, info: StmtInfo, failed: bool) -> dict[str, bool]:
        touched = set(info.reads) | set(info.writes)
        new_keys = {}
        changed: dict[str, bool] = {}  # имя → изменено ли на месте (а не перезаписано)
        for name, value in list(self.ns.items()):
            if name.startswith("__"):
                continue
            kind = classify(value)
            if kind in HIDDEN_KINDS:
                if kind in ("function", "class") and getattr(value, "__module__", None) == "__main__":
                    self.user_callables.add(name)
                continue
            limit = FULL_HASH_TOUCHED if name in touched else FULL_HASH_UNTOUCHED
            key = state_key(value, limit)
            new_keys[name] = key
            if name in info.writes and not failed:  # упавшая инструкция могла не дойти до присваивания
                changed[name] = False
            elif name not in self.keys:
                changed[name] = False  # появилось без явного присваивания (exec, цикл…)
            elif name in info.writes and keys_differ(self.keys[name], key):
                changed[name] = False  # упавшая инструкция успела перезаписать имя
            elif keys_differ(self.keys[name], key):
                changed[name] = True
        self.keys = new_keys
        return changed

    def _make_node(self, name, mutated, info, prev_latest, step_edges, step_notes):
        if self.node_count >= MAX_NODES:
            self.dropped += 1
            self.latest[name] = None
            return None
        value = self.ns[name]
        described = describe(name, value)
        size = len(repr(described))
        if described.get("preview") and size > self.preview_budget:
            described["preview"] = None
            described["truncated"] = True
            described["note"] = "Предпросмотр опущен: достигнут лимит размера схемы."
        self.preview_budget -= size

        self.seq += 1
        self.node_count += 1
        node_id = f"n{self.seq}"
        version = self.versions.get(name, 0) + 1
        self.versions[name] = version
        self.infos[node_id] = described

        partial = None
        if info.supported:
            sources = list(info.pairs.get(name, info.reads)) if not mutated else list(info.reads)
            if mutated and name not in sources:
                sources.append(name)
            funcs = [r for r in sources if r in self.user_callables]
            if funcs:
                partial = ", ".join(funcs[:2])
                self._note(
                    f"строка {info.start}: вызов функции {partial} — связи внутри неё не анализируются",
                    step_notes,
                )
            for src in sources:
                src_id = prev_latest.get(src)
                if src_id:
                    self._edge(src_id, node_id, info, src, prev_latest, step_edges)
        self.latest[name] = node_id

        return {
            "id": node_id, "type": "value", "name": name, "version": version,
            "lines": [[info.start, info.end]], "expr": info.exprs.get(name),
            "mutated": mutated, "partial": partial,
            "unsupported": None if info.supported else info.reason,
            "value": described,
        }

    def _edge(self, src_id, dst_id, info, src_name, prev_latest, step_edges):
        if (src_id, dst_id) in self.edge_set or self.edge_count >= MAX_EDGES:
            return
        edge = {"source": src_id, "target": dst_id}
        for array, mask in info.mask_uses:
            if array != src_name:
                continue
            mask_id = prev_latest.get(mask)
            a, m = self.infos.get(src_id), self.infos.get(mask_id or "")
            if a and m and m.get("kind") == "ndarray" and m.get("dtypeKind") == "bool" \
                    and a.get("shape") is not None and a.get("shape") == m.get("shape"):
                edge["mask"] = mask_id
                break
        self.edge_set.add((src_id, dst_id))
        self.edge_count += 1
        step_edges.append(edge)

    def _output_node(self, info, prev_latest, step_edges, text, truncated):
        if not self.output_lines or self.output_lines[-1] != [info.start, info.end]:
            self.output_lines.append([info.start, info.end])
        if info.supported:
            for name in info.reads:
                src_id = prev_latest.get(name)
                if src_id:
                    self._edge(src_id, "output", info, name, prev_latest, step_edges)
        return {
            "id": "output", "type": "output", "name": "output", "text": text, "truncated": truncated,
            "lines": [list(x) for x in self.output_lines],
            "unsupported": None if info.supported else info.reason,
        }


def run_program(code: str, filename: str, namespace: dict, send, out, build_error):
    """Выполняет code по инструкциям. Возвращает описание ошибки или None.

    SyntaxError всего файла бросается до выполнения чего-либо — как в обычном Python.
    """
    tree = ast.parse(code, filename=filename, mode="exec")
    tracer = Tracer(namespace, send)
    for stmt in tree.body:
        info = analyze_statement(stmt, code)
        send({"op": "begin", "line": info.start, "end": info.end})
        before = out.size
        error = None
        try:
            exec(compile(ast.Module(body=[stmt], type_ignores=[]), filename, "exec"), namespace)
        except BaseException as exc:  # включая SystemExit: воркер обязан пережить любой код
            error = build_error(exc)
        tracer.after_statement(info, error is not None, out.size > before, out.getvalue(), out.truncated)
        if error:
            return error
    return None
