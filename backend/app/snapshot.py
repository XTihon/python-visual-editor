"""Описание одного значения для схемы.

Работает внутри рабочего процесса. Всё превращается в строки и числа
(JSON-совместимые копии), поэтому последующее изменение массива не влияет
на уже сделанное описание. Размеры ограничены: большие объекты усекаются,
а усечение явно помечается.
"""
import reprlib
import types

import numpy as np

MAX_1D = 100
MAX_ROWS = 16
MAX_COLS = 16
MAX_REPR = 300
MAX_STR = 1000
MAX_ELEMENT_TEXT = 40
MAX_LIST_2D_ROWS = 10_000  # дальше не проверяем «прямоугольность» вложенных списков

_SCALAR_TYPES = (bool, int, float, complex, str, type(None))
_HIDDEN_KINDS = {"module", "function", "class"}

_short = reprlib.Repr()
_short.maxstring = 80
_short.maxother = MAX_REPR
_short.maxlist = 8
_short.maxtuple = 8
_short.maxdict = 6
_short.maxset = 8
_short.maxlevel = 3


def safe_repr(value, limit=MAX_REPR):
    try:
        text = _short.repr(value)
    except Exception as exc:  # repr пользовательского класса может падать
        return f"<не удалось получить repr: {type(exc).__name__}>"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _element_text(value):
    try:
        text = str(value)
    except Exception:
        return "?"
    return text if len(text) <= MAX_ELEMENT_TEXT else text[: MAX_ELEMENT_TEXT - 1] + "…"


def _dtype_kind(dtype):
    kind = dtype.kind
    if kind == "b":
        return "bool"
    if kind in "iu":
        return "int"
    if kind == "f":
        return "float"
    if kind == "c":
        return "complex"
    if kind in "US":
        return "str"
    return "other"


def _describe_ndarray(arr):
    info = {
        "kind": "ndarray",
        "shape": [int(n) for n in arr.shape],
        "dtype": str(arr.dtype),
        "ndim": int(arr.ndim),
        "size": int(arr.size),
        "dtypeKind": _dtype_kind(arr.dtype),
        "preview": None,
    }
    if arr.ndim == 0:
        info["repr"] = _element_text(arr[()])
        return info
    info["repr"] = safe_repr(arr)
    if arr.size == 0:
        info["note"] = "Пустой массив: в нём нет элементов."
        return info
    if arr.ndim == 1:
        part = arr[:MAX_1D]
        data = [_element_text(v) for v in part]
        shown = [len(data)]
    elif arr.ndim == 2:
        part = arr[:MAX_ROWS, :MAX_COLS]
        data = [[_element_text(v) for v in row] for row in part]
        shown = [len(data), len(data[0])]
    else:
        info["note"] = (
            f"Массив {arr.ndim}-мерный: подробная визуализация поддерживается только "
            "для 1D и 2D. Показаны метаданные."
        )
        return info
    shown_count = int(np.prod(shown))
    info["preview"] = {"data": data, "shownShape": shown, "hidden": int(arr.size) - shown_count}
    return info


def _list_dtype_kind(items):
    if not items:
        return "other"
    if all(type(x) is bool for x in items):
        return "bool"
    if all(type(x) is int for x in items):
        return "int"
    if all(type(x) in (int, float) for x in items):
        return "float"
    if all(isinstance(x, str) for x in items):
        return "str"
    return "other"


def _describe_list(seq):
    n = len(seq)
    info = {"kind": "list", "length": n, "repr": safe_repr(seq), "preview": None}
    if n == 0:
        info["note"] = "Пустой список."
        return info
    head = list(seq[:MAX_1D])
    rect_width = None
    if n <= MAX_LIST_2D_ROWS and all(isinstance(r, (list, tuple)) for r in seq):
        widths = {len(r) for r in seq}
        if len(widths) == 1 and widths != {0}:
            rect_width = widths.pop()
    if rect_width is not None:
        rows = [list(r[:MAX_COLS]) for r in seq[:MAX_ROWS]]
        flat = [x for r in rows for x in r]
        if all(isinstance(x, _SCALAR_TYPES) for x in flat):
            info["shape"] = [n, rect_width]
            info["dtypeKind"] = _list_dtype_kind(flat)
            data = [[_element_text(repr(x) if isinstance(x, str) else x) for x in r] for r in rows]
            shown = [len(data), len(data[0])]
            info["preview"] = {
                "data": data,
                "shownShape": shown,
                "hidden": n * rect_width - shown[0] * shown[1],
            }
            return info
    info["shape"] = [n]
    info["dtypeKind"] = _list_dtype_kind(head)
    data = [_element_text(repr(x) if isinstance(x, str) else safe_repr(x, MAX_ELEMENT_TEXT)) for x in head]
    info["preview"] = {"data": data, "shownShape": [len(data)], "hidden": n - len(data)}
    return info


def classify(value):
    if isinstance(value, np.ndarray):
        return "ndarray"
    if isinstance(value, (np.generic,) + _SCALAR_TYPES):
        return "str" if isinstance(value, (str, np.str_)) else "scalar"
    if isinstance(value, (list, tuple)):
        return "list"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, types.ModuleType):
        return "module"
    if isinstance(value, type):
        return "class"
    if isinstance(value, (types.FunctionType, types.BuiltinFunctionType, types.MethodType)):
        return "function"
    return "object"


def describe(name, value):
    """Описание одной переменной (без поля changed)."""
    kind = classify(value)
    info = {"name": name, "type": type(value).__name__, "kind": kind, "truncated": False}
    if kind == "ndarray":
        info.update(_describe_ndarray(value))
    elif kind == "list":
        info.update(_describe_list(value))
    elif kind == "str":
        text = str(value)
        info["length"] = len(text)
        info["repr"] = text[:MAX_STR]
        info["truncated"] = len(text) > MAX_STR
    elif kind == "dict":
        info["length"] = len(value)
        info["repr"] = safe_repr(value)
    elif kind == "scalar":
        info["repr"] = safe_repr(value)
        if isinstance(value, np.generic):
            info["dtype"] = str(value.dtype)
            info["repr"] = _element_text(value)
    else:
        info["repr"] = safe_repr(value)
    info["hidden"] = kind in _HIDDEN_KINDS
    if info["repr"] != "" and len(info["repr"]) >= MAX_REPR and kind in ("object", "dict", "list", "ndarray"):
        info["truncated"] = True
    if info.get("preview") and info["preview"]["hidden"] > 0:
        info["truncated"] = True
    return info
