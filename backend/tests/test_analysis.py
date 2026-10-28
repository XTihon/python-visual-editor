import ast

from app.analysis import analyze_statement


def info(code):
    tree = ast.parse(code)
    return analyze_statement(tree.body[0], code)


def test_simple_assignment_reads_and_writes():
    i = info("c = a + b * 2")
    assert i.writes == ["c"] and i.reads == ["a", "b"] and i.supported
    assert i.exprs["c"] == "a + b * 2"


def test_number_assignment_has_no_reads():
    i = info("A = 10")
    assert i.writes == ["A"] and i.reads == []


def test_augassign_reads_its_own_target():
    i = info("x += y")
    assert i.writes == ["x"] and set(i.reads) == {"x", "y"}


def test_subscript_store_is_a_read_not_a_write():
    i = info("a[i] = v")
    assert i.writes == [] and set(i.reads) == {"a", "i", "v"}


def test_tuple_unpacking_pairs():
    i = info("p, q = a, b + c")
    assert i.writes == ["p", "q"]
    assert i.pairs == {"p": ["a"], "q": ["b", "c"]}


def test_tuple_unpacking_from_call_has_no_pairs():
    i = info("p, q = f(a)")
    assert i.writes == ["p", "q"] and i.pairs == {}


def test_comprehension_local_names_are_not_reads():
    i = info("r = [x * k for x in data]")
    assert set(i.reads) == {"k", "data"}


def test_lambda_arguments_are_not_reads():
    i = info("f = lambda t: t + shift")
    assert i.reads == ["shift"]


def test_mask_use_detected_for_name_by_name_subscript():
    assert info("r = a[m]").mask_uses == [("a", "m")]
    assert info("r = a[a > 5]").mask_uses == []
    assert info("a[m] = 0").mask_uses == [("a", "m")]


def test_compound_statements_are_unsupported():
    for code, reason in [("for i in r:\n    s = s + i", "цикл for"), ("if a:\n    b = 1", "условие if"),
                         ("while a:\n    a -= 1", "цикл while"), ("with f() as h:\n    pass", "блок with")]:
        i = info(code)
        assert not i.supported and i.reason == reason and i.kind == "compound"


def test_dynamic_access_is_unsupported():
    assert not info("exec('x = 1')").supported
    assert not info("v = eval(s)").supported
    assert not info("g = globals()").supported


def test_definitions_and_imports():
    assert info("def f(x):\n    return x").defines == ["f"]
    assert info("class C: pass").defines == ["C"]
    assert info("import numpy as np").kind == "import"


def test_line_span_of_multiline_statement():
    i = info("x = (1 +\n     2)")
    assert (i.start, i.end) == (1, 2)


def test_walrus_target_is_a_write():
    i = info("print(y := a + 1)")
    assert "y" in i.writes and "a" in i.reads
