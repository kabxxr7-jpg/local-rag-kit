#!/usr/bin/env python3
"""Mutation check: put one small bug at a time into a throwaway copy of the code and see whether the offline tests notice.

    python scripts/mutation_check.py --validate          every mutant applies exactly once and still compiles (cheap)
    python scripts/mutation_check.py --list              what the mutants are
    python scripts/mutation_check.py                     the real run (waits for a calm machine first)
    python scripts/mutation_check.py --only chunk-overlap-ignored,ask-cites-everything-retrieved
    python scripts/mutation_check.py --json out.json --markdown out.md
    python scripts/mutation_check.py --selftest          planted hang, planted survivor, planted order-dependent test; nothing may be left running

Rules this runner keeps (each one has a reason, see docs/MUTATION.md):
  * one mutant at a time, on a copy in a temporary folder; the real files are never touched; the copy is deleted at the end
  * every pytest run is a process group of its own; on timeout the whole group gets SIGKILL and is reaped
  * a timeout is NOT a kill: it is reported as "timeout" and the run exits with 2
  * a kill needs a named failing test that fails again when its file runs alone; otherwise the status is "unconfirmed" (not a kill)
  * a load gate: the strict limits (load average < 6, at least 35 percent memory free) before the baseline, a looser pause (load < 10, 20 percent free) before each mutant
  * the unmutated copy must be green first, otherwise nothing is reported

Exit codes: 0 every mutant killed, 1 survivors or unconfirmed kills, 2 the run itself is not trustworthy (timeout, error, invalid mutant, baseline red, machine too busy).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from loadgate import Overloaded, wait_between, wait_for_calm  # noqa: E402
from procutil import RunResult, run_group  # noqa: E402

MIN_MUTANTS = 30
REQUIRED_AREAS = ("chunking", "dedupe", "threshold", "citations", "refusal", "prompt assembly", "config")
IGNORE = (".venv", ".git", ".work", ".mutation-*", "__pycache__", ".pytest_cache", ".rag-store", "*.egg-info", ".live-observations.jsonl", ".DS_Store")
REAL_PYTEST_ARGS = ["-m", "not live and not scenarios and not tooling"]
STATUSES = ("killed", "survived", "unconfirmed", "timeout", "error")


class MutantError(Exception):
    pass


# ---- applying a mutant ----------------------------------------------------------------------------------------------
def apply_mutant(text: str, m: dict) -> str:
    """Return the source with the mutant applied. `find` must occur exactly once, must change the text, and the result must compile."""
    n = text.count(m["find"])
    if n != 1:
        raise MutantError(f"{m['id']}: the text to replace occurs {n} times in {m['file']}; it must occur exactly once")
    new = text.replace(m["find"], m["replace"], 1)
    if new == text:
        raise MutantError(f"{m['id']}: replacing the text changes nothing")
    try:
        compile(new, m["file"], "exec")
    except SyntaxError as exc:
        raise MutantError(f"{m['id']}: the mutated file does not compile ({exc.msg}, line {exc.lineno})") from exc
    return new


def check_mutants(mutants: list[dict], root: Path, *, min_count: int = MIN_MUTANTS, required_areas=REQUIRED_AREAS) -> list[str]:
    """Problems with the mutant list, as plain sentences. Empty list means fine."""
    problems: list[str] = []
    ids = [m["id"] for m in mutants]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"the id {dup} is used more than once")
    if len(mutants) < min_count:
        problems.append(f"only {len(mutants)} mutants, at least {min_count} are required")
    missing = [a for a in required_areas if a not in {m["area"] for m in mutants}]
    if missing:
        problems.append("no mutant for: " + ", ".join(missing))
    for m in mutants:
        path = root / m["file"]
        if m["file"].startswith("tests/"):
            problems.append(f"{m['id']}: mutants belong in the code under test, not in tests")
            continue
        if not path.is_file():
            problems.append(f"{m['id']}: {m['file']} does not exist")
            continue
        try:
            apply_mutant(path.read_bytes().decode("utf-8"), m)
        except MutantError as exc:
            problems.append(str(exc))
    return problems


# ---- one pytest run ---------------------------------------------------------------------------------------------------
@dataclass
class Fail:
    file: str
    name: str
    collection: bool = False

    @property
    def nodeid(self) -> str:
        return f"{self.file}::{self.name}" if not self.collection else self.file


@dataclass
class Run:
    rr: RunResult
    fails: list[Fail]
    ran: int
    junit_ok: bool


def _file_of(tc: ET.Element, workdir: Path) -> str:
    f = tc.get("file")
    if f:
        return f
    parts = (tc.get("classname") or "").split(".")
    for cut in range(len(parts), 0, -1):  # tests.test_x.TestThing -> tests/test_x.py
        cand = Path(*parts[:cut]).with_suffix(".py")
        if (workdir / cand).is_file():
            return cand.as_posix()
    return tc.get("classname") or tc.get("name") or "?"


def parse_junit(path: Path, workdir: Path) -> tuple[list[Fail], int, bool]:
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError):
        return [], 0, False
    fails: list[Fail] = []
    ran = 0
    for tc in tree.iter("testcase"):
        classname = tc.get("classname") or ""
        failed = tc.find("failure") is not None or tc.find("error") is not None
        if tc.find("skipped") is None:
            ran += 1
        if failed:
            if classname == "" and not tc.get("file"):  # a collection error is reported as a nameless "test" for the module
                fails.append(Fail((tc.get("name") or "?").replace(".", "/") + ".py", "", True))
            else:
                fails.append(Fail(_file_of(tc, workdir), tc.get("name") or "?"))
    return fails, ran, True


def child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("LOCAL_RAG_") and k not in ("PYTHONPATH", "PYTEST_ADDOPTS")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # no stale bytecode from the previous mutant
    env["OMP_NUM_THREADS"] = "2"
    env["PYTHONHASHSEED"] = "0"
    return env


def clear_pycache(workdir: Path) -> None:
    for d in workdir.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def run_pytest(workdir: Path, junit: Path, targets: list[str], pytest_args: list[str], timeout: float) -> Run:
    junit.unlink(missing_ok=True)
    clear_pycache(workdir)
    argv = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "junit_family=xunit1", f"--junitxml={junit}", *pytest_args, *targets]
    rr = run_group(argv, cwd=str(workdir), env=child_env(), timeout=timeout)
    fails, ran, ok = parse_junit(junit, workdir)
    return Run(rr, fails, ran, ok)


# ---- the campaign ---------------------------------------------------------------------------------------------------
@dataclass
class Result:
    id: str
    area: str
    file: str
    what: str
    status: str = "error"
    killed_by: str = ""
    failing_tests: int = 0
    seconds: float = 0.0
    note: str = ""


@dataclass
class Campaign:
    label: str
    baseline_tests: int = 0
    baseline_seconds: float = 0.0
    results: list[Result] = field(default_factory=list)
    started: str = ""
    seconds: float = 0.0
    workdir_removed: bool = False
    aborted: str = ""
    baseline_output: str = ""

    def counts(self) -> dict[str, int]:
        return {s: sum(1 for r in self.results if r.status == s) for s in STATUSES}

    @property
    def exit_code(self) -> int:
        c = self.counts()
        if self.aborted or c["timeout"] or c["error"] or len(self.results) == 0:
            return 2
        if c["survived"] or c["unconfirmed"]:
            return 1
        return 0


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def judge(m: dict, workdir: Path, junit: Path, pytest_args: list[str], timeout: float, baseline_tests: int, first: Run) -> Result:
    res = Result(m["id"], m["area"], m["file"], m["what"])
    res.seconds = round(first.rr.seconds, 2)
    if first.rr.leftover:
        res.status, res.note = "error", "a process of the pytest run was still alive after the kill (must never happen)"
        return res
    if first.rr.timed_out:
        res.status, res.note = "timeout", f"no result within {timeout:.0f} s; the process group was killed; a timeout is not a kill"
        return res
    if first.rr.returncode == 0:
        if first.ran != baseline_tests:
            res.status, res.note = "error", f"pytest passed but ran {first.ran} tests, the baseline ran {baseline_tests}"
        else:
            res.status = "survived"
        return res
    res.failing_tests = len(first.fails)
    if not first.junit_ok or not first.fails or any(f.collection for f in first.fails):
        tail = " ".join(first.rr.output.strip().splitlines()[-3:])[:300]
        res.status, res.note = "error", f"pytest exited {first.rr.returncode} without a named failing test (collection or internal error?): {tail}"
        return res
    files: list[str] = []
    for f in first.fails:
        if f.file not in files:
            files.append(f.file)
    for file in files[:3]:
        wanted = {f.name for f in first.fails if f.file == file}
        again = run_pytest(workdir, junit, [file], pytest_args, timeout)
        res.seconds = round(res.seconds + again.rr.seconds, 2)
        if again.rr.leftover:
            res.status, res.note = "error", "a process of the confirmation run was still alive after the kill (must never happen)"
            return res
        if again.rr.timed_out:
            res.status, res.note = "timeout", f"the confirmation run of {file} did not finish within {timeout:.0f} s; killed; a timeout is not a kill"
            return res
        repeated = [f for f in again.fails if f.file == file and f.name in wanted and not f.collection]
        if repeated:
            res.status, res.killed_by = "killed", repeated[0].nodeid
            return res
    res.status = "unconfirmed"
    res.note = "tests failed in the full run, but none of them failed again when its file ran alone (" + ", ".join(files[:3]) + "); not counted as a kill"
    return res


def run_campaign(src: Path, mutants: list[dict], *, pytest_args: list[str], timeout: float, gate: bool = True, log=print, keep: bool = False, label: str = "repo", tmp_parent: str | None = None, start_gate: str = "strict") -> Campaign:
    camp = Campaign(label=label, started=time.strftime("%Y-%m-%d %H:%M:%S"))
    t0 = time.time()
    tmp = Path(tempfile.mkdtemp(prefix="mutation-", dir=tmp_parent))
    work = tmp / "work"
    junit = tmp / "junit.xml"
    try:
        shutil.copytree(src, work, ignore=shutil.ignore_patterns(*IGNORE))
        if gate:
            (wait_for_calm if start_gate == "strict" else wait_between)("the baseline run")
        base = run_pytest(work, junit, [], pytest_args, timeout * 2)
        camp.baseline_tests, camp.baseline_seconds = base.ran, round(base.rr.seconds, 2)
        if base.rr.timed_out or base.rr.returncode != 0 or base.rr.leftover:
            camp.aborted = "the unmutated copy is not green (" + ("timeout" if base.rr.timed_out else f"pytest exit {base.rr.returncode}") + "), nothing was mutated"
            camp.baseline_output = base.rr.output[-3000:]
            return camp
        log(f"baseline: {base.ran} tests green in {base.rr.seconds:.1f} s on a copy in {tmp}")
        for n, m in enumerate(mutants, 1):
            if gate:
                wait_between(f"mutant {m['id']}")
            target = work / m["file"]
            original = target.read_bytes()
            try:
                mutated = apply_mutant(original.decode("utf-8"), m)
            except MutantError as exc:
                camp.results.append(Result(m["id"], m["area"], m["file"], m["what"], "error", note=str(exc)))
                log(f"[{n:3}/{len(mutants)}] error      {m['id']}: {exc}")
                continue
            try:
                target.write_bytes(mutated.encode("utf-8"))
                first = run_pytest(work, junit, [], pytest_args, timeout)
                res = judge(m, work, junit, pytest_args, timeout, base.ran, first)
            finally:
                target.write_bytes(original)
            if _sha(target.read_bytes()) != _sha(original):
                raise RuntimeError(f"could not restore {m['file']} after {m['id']}")
            camp.results.append(res)
            extra = res.killed_by or res.note
            log(f"[{n:3}/{len(mutants)}] {res.status:<10} {m['id']:<42} {extra[:110]}")
    except Overloaded as exc:
        camp.aborted = str(exc)
        log(f"stopped: {exc}")
    finally:
        camp.seconds = round(time.time() - t0, 1)
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)
            camp.workdir_removed = not tmp.exists()
    return camp


# ---- reporting --------------------------------------------------------------------------------------------------------
def summary_line(camp: Campaign) -> str:
    c = camp.counts()
    total = len(camp.results)
    return f"{total} mutants: {c['killed']} killed, {c['survived']} survived, {c['unconfirmed']} unconfirmed, {c['timeout']} timeout, {c['error']} error"


def to_json(camp: Campaign) -> dict:
    return {
        "label": camp.label,
        "started": camp.started,
        "seconds": camp.seconds,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pytest_args": REAL_PYTEST_ARGS,
        "baseline_tests": camp.baseline_tests,
        "baseline_seconds": camp.baseline_seconds,
        "counts": camp.counts(),
        "total": len(camp.results),
        "aborted": camp.aborted,
        "results": [asdict(r) for r in camp.results],
    }


def render_markdown(camp: Campaign) -> str:
    lines = [f"Run started {camp.started}, {camp.seconds:.0f} s, baseline {camp.baseline_tests} tests green in {camp.baseline_seconds:.1f} s.", "", summary_line(camp) + ".", ""]
    lines += ["| # | mutant | area | the bug | result | killed by |", "|---|---|---|---|---|---|"]
    for n, r in enumerate(camp.results, 1):
        lines.append(f"| {n} | `{r.id}` | {r.area} | {r.what} | {r.status} | {('`' + r.killed_by + '`') if r.killed_by else (r.note or '')} |")
    return "\n".join(lines) + "\n"


# ---- the self test ----------------------------------------------------------------------------------------------------
def _selftest_project(root: Path, marker: str) -> list[dict]:
    (root / "tests").mkdir(parents=True)
    (root / "pytest.ini").write_text("[pytest]\npythonpath = .\naddopts = -p no:cacheprovider\n", encoding="utf-8")
    (root / "target.py").write_text(
        "def add(a, b):\n    return a + b\n\n\n"
        "def label(n):\n    return 'big' if n > 10 else 'small'\n\n\n"
        "def work():\n    return 1\n\n\n"
        "def pollute():\n    return False\n",
        encoding="utf-8",
    )
    (root / "tests" / "conftest.py").write_text(
        "from pathlib import Path\n\n\ndef pytest_sessionstart(session):\n    Path('polluted').unlink(missing_ok=True)\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_target.py").write_text(
        "from target import add, label, work\n\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n\n\n"
        "def test_label_far_from_the_boundary():\n    assert label(100) == 'big'\n    assert label(1) == 'small'\n\n\n"
        "def test_work():\n    assert work() == 1\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_aa_pollute.py").write_text(
        "from pathlib import Path\n\nfrom target import pollute\n\n\n"
        "def test_pollute():\n    if pollute():\n        Path('polluted').write_text('x')\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_zz_clean.py").write_text(
        "from pathlib import Path\n\n\ndef test_nothing_left_behind():\n    assert not Path('polluted').exists()\n",
        encoding="utf-8",
    )
    hang = (
        "def work():\n    import subprocess, sys, time\n"
        f"    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)', '{marker}'])\n"
        "    time.sleep(600)\n    return 1\n"
    )
    return [
        dict(id="add-minus", area="selftest", file="target.py", what="addition becomes subtraction (must be killed)", find="return a + b", replace="return a - b"),
        dict(id="label-boundary", area="selftest", file="target.py", what="boundary moved by one, no test looks there (must survive)", find="n > 10", replace="n >= 10"),
        dict(id="work-hangs", area="selftest", file="target.py", what="starts a child process and sleeps forever (must time out, child must be gone)", find="def work():\n    return 1\n", replace=hang),
        dict(id="pollute-order", area="selftest", file="target.py", what="fails only after another test file ran first (must be unconfirmed)", find="def pollute():\n    return False", replace="def pollute():\n    return True"),
    ]


def processes_matching(marker: str) -> list[str]:
    out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, timeout=20).stdout
    me = os.getpid()
    return [ln.strip() for ln in out.splitlines() if marker in ln and not ln.strip().startswith(f"{me} ")]


def selftest(log=print) -> int:
    marker = "lrk-selftest-" + uuid.uuid4().hex
    base = Path(tempfile.mkdtemp(prefix="mutation-selftest-"))
    camp = None
    try:
        project = base / "project"
        mutants = _selftest_project(project, marker)
        camp = run_campaign(project, mutants, pytest_args=[], timeout=8, gate=False, log=log, label="selftest", tmp_parent=str(base))
    finally:
        pass
    expected = {"add-minus": "killed", "label-boundary": "survived", "work-hangs": "timeout", "pollute-order": "unconfirmed"}
    got = {r.id: r.status for r in camp.results}
    problems = []
    for k, v in expected.items():
        if got.get(k) != v:
            problems.append(f"{k}: expected {v}, got {got.get(k)}")
    if camp.aborted:
        problems.append("campaign aborted: " + camp.aborted)
    killed = next((r for r in camp.results if r.id == "add-minus"), None)
    if killed and not killed.killed_by.startswith("tests/test_target.py::test_add"):
        problems.append(f"add-minus should be killed by tests/test_target.py::test_add, was {killed.killed_by!r}")
    left = processes_matching(marker)
    if left:
        problems.append("processes still running after the run: " + "; ".join(left))
    if not camp.workdir_removed:
        problems.append("the temporary copy was not removed")
    shutil.rmtree(base, ignore_errors=True)
    if base.exists():
        problems.append("the selftest folder was not removed")
    if problems:
        log("SELFTEST FAILED")
        for p in problems:
            log("  - " + p)
        return 1
    log("SELFTEST OK: killed, survived, timeout and unconfirmed all reported as expected; no process left; temporary folders removed")
    return 0


# ---- command line -----------------------------------------------------------------------------------------------------
def load_mutants() -> list[dict]:
    from mutants import MUTANTS

    return list(MUTANTS)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mutation check for local-rag-kit (see the top of this file).")
    ap.add_argument("--list", action="store_true", help="list the mutants")
    ap.add_argument("--validate", action="store_true", help="check that every mutant applies exactly once and compiles; run nothing")
    ap.add_argument("--selftest", action="store_true", help="prove the runner itself: planted hang, survivor and order-dependent test")
    ap.add_argument("--only", action="append", default=[], help="mutant ids, comma separated (repeatable)")
    ap.add_argument("--timeout", type=float, default=120.0, help="seconds per pytest run before the process group is killed (default 120)")
    ap.add_argument("--no-gate", action="store_true", help="skip the load gate (not for the real run)")
    ap.add_argument("--start-gate", choices=["strict", "between"], default="strict", help="strict: load < 6 and at least 35% memory free before the baseline. between: the looser limits (directly after another job that passed the strict gate)")
    ap.add_argument("--keep", action="store_true", help="keep the temporary copy")
    ap.add_argument("--json", metavar="PATH", help="write the results as JSON")
    ap.add_argument("--markdown", metavar="PATH", help="write the results as a Markdown table")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    mutants = load_mutants()
    if args.list:
        for m in mutants:
            print(f"{m['id']:<42} {m['area']:<16} {m['file']:<22} {m['what']}")
        return 0
    problems = check_mutants(mutants, ROOT)
    if args.validate:
        for p in problems:
            print("PROBLEM:", p)
        print(f"{len(mutants)} mutants, {len(problems)} problems")
        return 1 if problems else 0
    if problems:
        for p in problems:
            print("PROBLEM:", p)
        print("not running: fix the mutant list first (python scripts/mutation_check.py --validate)")
        return 2
    chosen = [x for chunk in args.only for x in chunk.split(",") if x]
    if chosen:
        unknown = [c for c in chosen if c not in {m["id"] for m in mutants}]
        if unknown:
            print("unknown mutant ids:", ", ".join(unknown))
            return 2
        mutants = [m for m in mutants if m["id"] in chosen]
    try:
        os.nice(10)
    except OSError:
        pass
    camp = run_campaign(ROOT, mutants, pytest_args=REAL_PYTEST_ARGS, timeout=args.timeout, gate=not args.no_gate, keep=args.keep, start_gate=args.start_gate)
    print()
    if camp.aborted:
        print("ABORTED:", camp.aborted)
        if camp.baseline_output:
            print(camp.baseline_output)
    print(summary_line(camp) + f" in {camp.seconds:.0f} s")
    for r in camp.results:
        if r.status != "killed":
            print(f"  {r.status.upper():<11} {r.id}: {r.what} {('-- ' + r.note) if r.note else ''}")
    if args.json:
        Path(args.json).write_text(json.dumps(to_json(camp), indent=1) + "\n", encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(render_markdown(camp), encoding="utf-8")
    return camp.exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Overloaded as exc:
        print("machine too busy:", exc, file=sys.stderr)
        sys.exit(2)
