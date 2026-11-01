"""Tests of the tools in scripts/ (mutation runner, process helper, load gate). Marked `tooling`: the mutation check leaves them out."""
from __future__ import annotations

import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import loadgate  # noqa: E402
import mutation_check as mc  # noqa: E402
import procutil  # noqa: E402

pytestmark = pytest.mark.tooling


def mutant(**kw):
    base = dict(id="m", area="chunking", file="x.py", what="w", find="a", replace="b")
    base.update(kw)
    return base


# ---- the mutant list ------------------------------------------------------------------------------------------------
def test_every_mutant_applies_exactly_once_and_compiles():
    assert mc.check_mutants(mc.load_mutants(), ROOT) == []


def test_there_are_enough_mutants_over_the_required_areas():
    ms = mc.load_mutants()
    assert len(ms) >= mc.MIN_MUTANTS
    assert {m["area"] for m in ms} >= set(mc.REQUIRED_AREAS)
    assert len({m["id"] for m in ms}) == len(ms)


def test_mutants_only_touch_the_package():
    assert all(m["file"].startswith("local_rag/") for m in mc.load_mutants())


def test_apply_replaces_exactly_one_place():
    assert mc.apply_mutant("x = 1\ny = 2\n", mutant(find="x = 1", replace="x = 2")) == "x = 2\ny = 2\n"


@pytest.mark.parametrize(
    "text,find,replace,words",
    [
        ("x = 1\n", "y = 1", "y = 2", "0 times"),
        ("x = 1\nx = 1\n", "x = 1", "x = 2", "2 times"),
        ("x = 1\n", "x = 1", "x = 1", "changes nothing"),
        ("x = 1\n", "x = 1", "x = (", "does not compile"),
    ],
)
def test_apply_refuses_what_it_cannot_do_cleanly(text, find, replace, words):
    with pytest.raises(mc.MutantError, match=words):
        mc.apply_mutant(text, mutant(find=find, replace=replace))


def test_check_mutants_reports_problems_in_plain_words(tmp_path):
    (tmp_path / "x.py").write_text("a = 1\n", encoding="utf-8")
    ms = [mutant(id="one"), mutant(id="one", file="tests/test_y.py"), mutant(id="two", file="missing.py")]
    problems = " | ".join(mc.check_mutants(ms, tmp_path, min_count=5, required_areas=("dedupe",)))
    for fragment in ("used more than once", "at least 5", "no mutant for: dedupe", "belong in the code under test", "does not exist"):
        assert fragment in problems


# ---- reading pytest results -------------------------------------------------------------------------------------------
JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="5">
<testcase classname="tests.test_a" name="test_ok" file="tests/test_a.py" time="0.1"/>
<testcase classname="tests.test_a" name="test_bad[x]" file="tests/test_a.py" time="0.1"><failure message="boom">trace</failure></testcase>
<testcase classname="tests.test_b" name="test_err" file="tests/test_b.py" time="0.1"><error message="fixture">trace</error></testcase>
<testcase classname="tests.test_b" name="test_skip" file="tests/test_b.py" time="0.0"><skipped message="s"/></testcase>
<testcase classname="" name="tests.test_c" time="0.0"><error message="collection failure">trace</error></testcase>
</testsuite></testsuites>
"""


def test_parse_junit_names_failures_errors_and_collection_problems(tmp_path):
    f = tmp_path / "j.xml"
    f.write_text(JUNIT, encoding="utf-8")
    fails, ran, ok = mc.parse_junit(f, tmp_path)
    assert ok and ran == 4  # the skipped one did not run
    assert [(x.file, x.name, x.collection) for x in fails] == [
        ("tests/test_a.py", "test_bad[x]", False),
        ("tests/test_b.py", "test_err", False),
        ("tests/test_c.py", "", True),
    ]
    assert fails[0].nodeid == "tests/test_a.py::test_bad[x]"


def test_parse_junit_of_a_missing_or_broken_file_is_not_ok(tmp_path):
    assert mc.parse_junit(tmp_path / "nope.xml", tmp_path)[2] is False
    broken = tmp_path / "b.xml"
    broken.write_text("<testsuite", encoding="utf-8")
    assert mc.parse_junit(broken, tmp_path)[2] is False


def test_the_child_environment_is_clean(monkeypatch):
    monkeypatch.setenv("LOCAL_RAG_K", "99")
    monkeypatch.setenv("PYTHONPATH", "/somewhere")
    monkeypatch.setenv("PYTEST_ADDOPTS", "-x")
    env = mc.child_env()
    assert "LOCAL_RAG_K" not in env and "PYTHONPATH" not in env and "PYTEST_ADDOPTS" not in env
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


def test_json_and_markdown_reports_carry_every_mutant():
    camp = mc.Campaign(label="t", started="now", baseline_tests=3)
    camp.results = [mc.Result("a", "x", "f.py", "bug a", "killed", "tests/t.py::test_a"), mc.Result("b", "x", "f.py", "bug b", "survived")]
    data = mc.to_json(camp)
    assert data["counts"]["killed"] == 1 and data["counts"]["survived"] == 1 and data["total"] == 2
    md = mc.render_markdown(camp)
    assert "`a`" in md and "tests/t.py::test_a" in md and "survived" in md
    assert camp.exit_code == 1


def test_exit_codes():
    camp = mc.Campaign(label="t")
    assert camp.exit_code == 2  # no result at all is not a pass
    camp.results = [mc.Result("a", "x", "f", "w", "killed")]
    assert camp.exit_code == 0
    camp.results.append(mc.Result("b", "x", "f", "w", "unconfirmed"))
    assert camp.exit_code == 1
    camp.results.append(mc.Result("c", "x", "f", "w", "timeout"))
    assert camp.exit_code == 2
    camp.results = [mc.Result("a", "x", "f", "w", "killed")]
    camp.aborted = "baseline red"
    assert camp.exit_code == 2


# ---- processes ----------------------------------------------------------------------------------------------------------
def test_run_group_kills_the_whole_group_on_timeout():
    marker = "lrk-test-" + uuid.uuid4().hex
    code = f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)', '{marker}']); time.sleep(300)"
    started = time.time()
    res = procutil.run_group([sys.executable, "-c", code], cwd=str(ROOT), env={"PATH": "/usr/bin:/bin"}, timeout=2)
    assert res.timed_out and res.returncode is None and not res.leftover
    assert time.time() - started < 30
    assert mc.processes_matching(marker) == []


def test_run_group_reports_exit_code_and_output():
    res = procutil.run_group([sys.executable, "-c", "print('hello'); raise SystemExit(3)"], cwd=str(ROOT), env={"PATH": "/usr/bin:/bin"}, timeout=20)
    assert (res.returncode, res.timed_out, res.leftover) == (3, False, False)
    assert "hello" in res.output


def test_run_group_cleans_up_when_the_caller_is_interrupted(monkeypatch):
    marker = "lrk-test-" + uuid.uuid4().hex
    code = f"import time, sys; time.sleep(300)  # {marker}"
    real = subprocess.Popen.communicate

    def boom(self, *a, **kw):
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess.Popen, "communicate", boom)
    with pytest.raises(KeyboardInterrupt):
        procutil.run_group([sys.executable, "-c", code], cwd=str(ROOT), env={"PATH": "/usr/bin:/bin"}, timeout=60)
    monkeypatch.setattr(subprocess.Popen, "communicate", real)
    assert mc.processes_matching(marker) == []


# ---- load gate ----------------------------------------------------------------------------------------------------------
def test_load_gate_gives_up_instead_of_running_on_a_busy_machine():
    with pytest.raises(loadgate.Overloaded, match="giving up"):
        loadgate.wait_for_calm("a test", max_load=0.0, max_swap_mb=1e9, poll=0.05, max_wait_minutes=0.002)


def test_load_gate_lets_a_calm_machine_through():
    loadgate.wait_for_calm("a test", max_load=1e6, max_swap_mb=1e9, poll=0.05, max_wait_minutes=0.1)


def test_load_gate_limits_are_the_ones_that_were_asked_for():
    assert loadgate.MAX_LOAD == 6.0 and loadgate.MAX_SWAP_MB == 4000.0 and loadgate.MAX_WAIT_MINUTES == 20
