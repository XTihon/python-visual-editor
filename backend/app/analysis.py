"""Статический разбор инструкции верхнего уровня: что она читает и что записывает.

Это единственный источник «связей» в схеме: стрелка a → b появляется, только если
инструкция, создавшая b, буквально читает имя a. Модуль не знает значений и ничего
не выполняет. Для конструкций, где такой вывод ненадёжен (циклы, условия, with, try,
exec/eval), supported=False — тогда схема показывает значения, но не рисует связи.
"""
import ast
from dataclasses import dataclass, field

DYNAMIC_NAMES = {"exec", "eval", "globals", "locals", "vars", "compile", "__import__"}

COMPOUND_LABELS = {
    "For": "цикл for", "AsyncFor": "цикл for", "While": "цикл while", "If": "условие if",
    "With": "блок with", "AsyncWith": "блок with", "Try": "блок try", "TryStar": "блок try",
    "Match": "оператор match",
}
MAX_EXPR_CHARS = 80


@dataclass
class StmtInfo:
    start: int
    end: int
    kind: str  # simple | import | definition | compound
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    # имя цели → что читает именно её выражение (для a, b = x, y)
    pairs: dict[str, list[str]] = field(default_factory=dict)
    exprs: dict[str, str] = field(default_factory=dict)  # имя цели → текст выражения
    mask_uses: list[tuple[str, str]] = field(default_factory=list)  # (массив, маска) из a[mask]
    defines: list[str] = field(default_factory=list)  # имена def/class
    supported: bool = True
    reason: str | None = None


class _Reads(ast.NodeVisitor):
    """Имена, читаемые выражением; локальные имена comprehension и lambda исключаются."""

    def __init__(self):
        self.names: list[str] = []
        self._bound: list[set[str]] = []

    def _add(self, name: str):
        if name not in self.names and not any(name in scope for scope in self._bound):
            self.names.append(name)

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            self._add(node.id)

    def _comprehension(self, node):
        scope = {n.id for gen in node.generators for n in ast.walk(gen.target) if isinstance(n, ast.Name)}
        self._bound.append(scope)
        self.generic_visit(node)
        self._bound.pop()

    visit_ListComp = visit_SetComp = visit_DictComp = visit_GeneratorExp = _comprehension

    def visit_Lambda(self, node: ast.Lambda):
        for default in node.args.defaults + [d for d in node.args.kw_defaults if d is not None]:
            self.visit(default)
        a = node.args
        scope = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
        scope |= {x.arg for x in (a.vararg, a.kwarg) if x is not None}
        self._bound.append(scope)
        self.visit(node.body)
        self._bound.pop()


def reads_of(*nodes: ast.AST) -> list[str]:
    visitor = _Reads()
    for node in nodes:
        visitor.visit(node)
    return visitor.names


def _stored_names(node: ast.AST) -> list[str]:
    out: list[str] = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id not in out:
            out.append(n.id)
    return out


def _target_names(target: ast.AST) -> list[str]:
    """Имена, которым присваивается значение (a, (b, *c)); a[i] и a.x — это не новые имена."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [n for elt in target.elts for n in _target_names(elt)]
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    return []


def _segment(source: str, node: ast.AST) -> str | None:
    text = ast.get_source_segment(source, node)
    if text is None:
        return None
    text = " ".join(text.split())
    return text if len(text) <= MAX_EXPR_CHARS else text[: MAX_EXPR_CHARS - 1] + "…"


def _mask_uses(node: ast.AST) -> list[tuple[str, str]]:
    uses = []
    for n in ast.walk(node):
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and isinstance(n.slice, ast.Name):
            pair = (n.value.id, n.slice.id)
            if pair not in uses:
                uses.append(pair)
    return uses


def analyze_statement(stmt: ast.stmt, source: str) -> StmtInfo:
    start = min([stmt.lineno] + [d.lineno for d in getattr(stmt, "decorator_list", [])])
    info = StmtInfo(start=start, end=stmt.end_lineno or stmt.lineno, kind="simple")

    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        info.kind = "definition"
        info.defines = [stmt.name]
        return info
    if isinstance(stmt, (ast.Import, ast.ImportFrom)):
        info.kind = "import"
        return info

    kind = type(stmt).__name__
    if kind in COMPOUND_LABELS:
        info.kind = "compound"
        info.supported = False
        info.reason = COMPOUND_LABELS[kind]
        info.writes = _stored_names(stmt)
        info.reads = reads_of(stmt)
        return info

    if isinstance(stmt, ast.Assign):
        info.reads = reads_of(stmt.value, *stmt.targets)
        for target in stmt.targets:
            info.writes += [n for n in _target_names(target) if n not in info.writes]
        value_text = _segment(source, stmt.value)
        for name in info.writes:
            if value_text:
                info.exprs[name] = value_text
        if len(stmt.targets) == 1 and isinstance(stmt.targets[0], (ast.Tuple, ast.List)) \
                and isinstance(stmt.value, (ast.Tuple, ast.List)):
            targets, values = stmt.targets[0].elts, stmt.value.elts
            if len(targets) == len(values) and not any(isinstance(e, ast.Starred) for e in targets + values):
                for t, v in zip(targets, values):
                    for name in _target_names(t):
                        info.pairs[name] = reads_of(v)
                        text = _segment(source, v)
                        if text:
                            info.exprs[name] = text
    elif isinstance(stmt, ast.AugAssign):
        info.reads = reads_of(stmt.value, stmt.target)
        if isinstance(stmt.target, ast.Name):
            info.writes = [stmt.target.id]
            if stmt.target.id not in info.reads:
                info.reads.append(stmt.target.id)
            text = _segment(source, stmt)
            if text:
                info.exprs[stmt.target.id] = text
    elif isinstance(stmt, ast.AnnAssign):
        info.reads = reads_of(*(n for n in (stmt.value, stmt.target) if n is not None))
        if stmt.value is not None and isinstance(stmt.target, ast.Name):
            info.writes = [stmt.target.id]
            text = _segment(source, stmt.value)
            if text:
                info.exprs[stmt.target.id] = text
    else:
        info.reads = reads_of(stmt)

    # a := expr внутри простой инструкции
    for n in ast.walk(stmt):
        if isinstance(n, ast.NamedExpr) and n.target.id not in info.writes:
            info.writes.append(n.target.id)

    info.mask_uses = _mask_uses(stmt)
    if DYNAMIC_NAMES & set(info.reads):
        info.supported = False
        info.reason = "динамический доступ к переменным (exec/eval/globals…)"
    return info
