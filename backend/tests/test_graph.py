"""Значения и связи схемы — по настоящему выполнению Python."""
from tests.conftest import by_name, edges, nodes

SPEC_EXAMPLE = """import numpy as np

a = np.array([2, 7, 4, 9])
mask = a > 5
result = a[mask]
print(result)
"""


def test_single_number_assignment(api):
    run = api.run("A = 10")
    [node] = nodes(run)
    assert node["name"] == "A" and node["value"]["repr"] == "10" and node["value"]["kind"] == "scalar"
    assert node["lines"] == [[1, 1]]
    assert run["graph"]["edges"] == []


def test_spec_example_values_and_edges(api):
    run = api.run(SPEC_EXAMPLE)
    v = by_name(run)
    assert v["a"][0]["value"]["preview"]["data"] == ["2", "7", "4", "9"]
    assert v["mask"][0]["value"]["preview"]["data"] == ["False", "True", "False", "True"]
    assert v["mask"][0]["value"]["dtypeKind"] == "bool"
    assert v["result"][0]["value"]["preview"]["data"] == ["7", "9"]
    [output] = nodes(run, "output")
    assert output["text"] == "[7 9]\n" == run["stdout"]
    assert output["lines"] == [[6, 6]]
    # ровно четыре связи по зависимостям данных; np — модуль, узла у него нет
    assert edges(run) == {("a#1", "mask#1"), ("a#1", "result#1"), ("mask#1", "result#1"), ("result#1", "output")}
    assert set(by_name(run)) == {"a", "mask", "result"}  # нет узлов для np


def test_mask_edge_is_marked_for_automatic_highlight(api):
    run = api.run(SPEC_EXAMPLE)
    ids = {(n["name"]): n["id"] for n in nodes(run)}
    marked = [e for e in run["graph"]["edges"] if "mask" in e]
    assert marked == [{"source": ids["a"], "target": ids["result"], "mask": ids["mask"]}]


def test_expression_text_is_kept_from_source(api):
    run = api.run(SPEC_EXAMPLE)
    assert by_name(run)["mask"][0]["expr"] == "a > 5"
    assert by_name(run)["result"][0]["expr"] == "a[mask]"


def test_reassignment_creates_versions_with_independent_values(api):
    run = api.run("x = 1\ny = x + 1\nx = x * 10\nz = x + y")
    v = by_name(run)
    assert [n["value"]["repr"] for n in v["x"]] == ["1", "10"]
    assert [n["version"] for n in v["x"]] == [1, 2]
    assert edges(run) == {("x#1", "y#1"), ("x#1", "x#2"), ("x#2", "z#1"), ("y#1", "z#1")}


def test_reassignment_to_same_value_is_still_a_new_version(api):
    run = api.run("A = 10\nA = 10")
    assert [n["version"] for n in by_name(run)["A"]] == [1, 2]


def test_in_place_change_keeps_previous_snapshot(api):
    run = api.run("import numpy as np\na = np.array([1, 2, 3])\nb = a * 2\na[0] = 99\nc = a + 1")
    v = by_name(run)
    assert [n["value"]["preview"]["data"] for n in v["a"]] == [["1", "2", "3"], ["99", "2", "3"]]
    assert v["a"][1]["mutated"] is True and v["a"][0]["mutated"] is False
    assert v["b"][0]["value"]["preview"]["data"] == ["2", "4", "6"]
    assert edges(run) == {("a#1", "b#1"), ("a#1", "a#2"), ("a#2", "c#1")}  # b зависит от старой версии a


def test_in_place_method_call_and_augassign(api):
    run = api.run("lst = [3, 1, 2]\nlst.sort()\nlst.append(7)\nn = len(lst)")
    v = by_name(run)
    assert [n["value"]["preview"]["data"] for n in v["lst"]] == [["3", "1", "2"], ["1", "2", "3"], ["1", "2", "3", "7"]]
    assert ("lst#3", "n#1") in edges(run)


def test_alias_mutation_updates_both_names(api):
    run = api.run("import numpy as np\na = np.array([1, 2])\nb = a\nb[0] = 5")
    v = by_name(run)
    assert len(v["a"]) == 2 and len(v["b"]) == 2
    assert v["a"][1]["value"]["preview"]["data"] == ["5", "2"]
    assert ("a#1", "a#2") in edges(run) and ("b#1", "a#2") in edges(run)


def test_reshape_and_matrix_values(api):
    run = api.run("import numpy as np\nm = np.arange(6).reshape(2, 3)\nn = m.reshape(3, 2)\nprint(n.shape)")
    v = by_name(run)
    assert v["m"][0]["value"]["shape"] == [2, 3]
    assert v["m"][0]["value"]["preview"]["data"] == [["0", "1", "2"], ["3", "4", "5"]]
    assert v["n"][0]["value"]["preview"]["data"] == [["0", "1"], ["2", "3"], ["4", "5"]]
    assert edges(run) == {("m#1", "n#1"), ("n#1", "output")}


def test_lists_arithmetic_and_comparison(api):
    run = api.run("nums = [4, 8, 15]\ntotal = sum(nums)\nbig = total > 20\nratio = total / 3")
    v = by_name(run)
    assert v["nums"][0]["value"]["preview"]["data"] == ["4", "8", "15"]
    assert v["total"][0]["value"]["repr"] == "27" and v["big"][0]["value"]["repr"] == "True"
    assert edges(run) == {("nums#1", "total#1"), ("total#1", "big#1"), ("total#1", "ratio#1")}


def test_tuple_unpacking_links_only_matching_parts(api):
    run = api.run("a = 1\nb = 2\np, q = b, a + 10")
    assert edges(run) == {("b#1", "p#1"), ("a#1", "q#1")}


def test_multiple_prints_feed_one_output_block(api):
    run = api.run("a = 1\nb = 2\nprint(a)\nprint(b)\nprint('x')")
    [output] = nodes(run, "output")
    assert output["text"] == "1\n2\nx\n"
    assert output["lines"] == [[3, 3], [4, 4], [5, 5]]
    assert edges(run) == {("a#1", "output"), ("b#1", "output")}


def test_print_uses_value_of_the_moment(api):
    run = api.run("x = 1\nprint(x)\nx = 2\nprint(x)")
    # x = 2 не читает старый x, поэтому x#1 → x#2 нет; print берёт значение на момент вызова
    assert edges(run) == {("x#1", "output"), ("x#2", "output")}


def test_imports_and_functions_are_not_data_nodes(api):
    run = api.run("import math\nfrom math import sqrt\ndef f(v):\n    return v + 1\nclass K:\n    pass\nr = f(2)\ns = sqrt(16)")
    assert set(by_name(run)) == {"r", "s"}


def test_unsupported_loop_shows_values_without_invented_edges(api):
    run = api.run("total = 0\nfor i in range(4):\n    total = total + i\nprint(total)")
    v = by_name(run)
    assert v["total"][-1]["value"]["repr"] == "6"
    assert v["total"][-1]["unsupported"] == "цикл for" and v["i"][0]["unsupported"] == "цикл for"
    assert not any(t in ("total#2", "i#1") for _, t in edges(run))  # к узлам цикла связи не рисуются
    assert any("цикл for" in note for note in run["graph"]["notes"])
    assert run["stdout"] == "6\n"


def test_unsupported_exec_and_if(api):
    run = api.run("exec('k = 5')\nflag = True\nif flag:\n    m = 3")
    v = by_name(run)
    assert v["k"][0]["value"]["repr"] == "5" and v["m"][0]["value"]["repr"] == "3"
    assert edges(run) == set()
    assert len(run["graph"]["notes"]) == 2


def test_user_function_call_is_marked_partial(api):
    run = api.run("def double(x):\n    return x * 2\na = 4\nb = double(a)")
    node = by_name(run)["b"][0]
    assert node["partial"] == "double" and node["value"]["repr"] == "8"
    assert ("a#1", "b#1") in edges(run)
    assert any("double" in note for note in run["graph"]["notes"])


def test_failed_statement_does_not_create_a_fake_version(api):
    run = api.run("x = 1\nx = 1 / 0")
    assert run["status"] == "error" and run["error"]["line"] == 2
    assert [n["version"] for n in by_name(run)["x"]] == [1]


def test_error_keeps_earlier_values_and_reports_line(api):
    run = api.run("a = 5\nb = a * 2\nc = b / 0\nd = 1")
    assert run["status"] == "error"
    assert run["error"]["type"] == "ZeroDivisionError" and run["error"]["line"] == 3
    assert "Traceback" in run["error"]["text"]
    assert set(by_name(run)) == {"a", "b"}


def test_error_inside_loop_reports_exact_line(api):
    run = api.run("items = [1, 2, 0]\nfor v in items:\n    r = 10 / v\n")
    assert run["error"]["line"] == 3
    assert by_name(run)["items"][0]["value"]["repr"] == "[1, 2, 0]"


def test_syntax_error_runs_nothing(api):
    run = api.run("a = 1\nb = (2 +\nprint(")
    assert run["status"] == "error" and run["error"]["kind"] == "syntax"
    assert run["error"]["line"] is not None
    assert run["graph"]["nodes"] == []


def test_big_array_and_empty_array_previews(api):
    run = api.run("import numpy as np\nbig = np.zeros((1000, 1000))\nlong1d = np.arange(5000)\nempty = np.array([])\n"
                  "weird = np.array([1.0, np.nan, np.inf])\ncube = np.zeros((2, 3, 4))")
    v = by_name(run)
    assert v["big"][0]["value"]["preview"]["shownShape"] == [16, 16]
    assert v["big"][0]["value"]["preview"]["hidden"] == 1_000_000 - 256
    assert v["big"][0]["value"]["truncated"] is True
    assert v["long1d"][0]["value"]["preview"]["shownShape"] == [100]
    assert v["empty"][0]["value"]["preview"] is None and "Пустой" in v["empty"][0]["value"]["note"]
    assert v["weird"][0]["value"]["preview"]["data"] == ["1.0", "nan", "inf"]
    assert v["cube"][0]["value"]["preview"] is None and "3-мерный" in v["cube"][0]["value"]["note"]


def test_graph_is_capped_and_truncation_is_reported(api):
    run = api.run("\n".join(f"v{i} = {i}" for i in range(120)))
    assert len(nodes(run)) == 80
    assert run["graph"]["dropped"] == 40


def test_each_run_starts_clean(api):
    api.run("leftover = 1")
    run = api.run("print('leftover' in globals())")
    assert run["stdout"] == "False\n"


def test_line_ranges_of_multiline_statement(api):
    run = api.run("x = [1,\n     2,\n     3]\ny = len(x)")
    assert by_name(run)["x"][0]["lines"] == [[1, 3]] and by_name(run)["y"][0]["lines"] == [[4, 4]]


def test_aliasing_does_not_leak_snapshots_between_versions(api):
    run = api.run("data = [1, 2]\nsnapshot = list(data)\ndata.append(3)")
    v = by_name(run)
    assert v["snapshot"][0]["value"]["preview"]["data"] == ["1", "2"]
    assert v["data"][1]["value"]["preview"]["data"] == ["1", "2", "3"]


def test_dict_value_change_creates_new_version(api):
    run = api.run("d = {'a': 1}\nd['a'] = 2\nprint(d)")
    versions = by_name(run)["d"]
    assert [n["value"]["repr"] for n in versions] == ["{'a': 1}", "{'a': 2}"]
    assert versions[1]["mutated"] is True and versions[0]["mutated"] is False
    assert run["stdout"] == "{'a': 2}\n"


def test_dict_nested_change_does_not_create_version(api):
    run = api.run("d = {'k': []}\nd['k'].append(1)")
    assert len(by_name(run)["d"]) == 1  # README: вложенное изменение без смены верхнего объекта не замечается


def test_dict_new_key_creates_new_version(api):
    run = api.run("d = {'a': 1}\nd['b'] = 3")
    assert [n["value"]["repr"] for n in by_name(run)["d"]] == ["{'a': 1}", "{'a': 1, 'b': 3}"]
