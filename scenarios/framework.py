"""The "fix an inherited pipeline" lab.

A scenario is a deliberately broken copy (or setting) of the pipeline, a symptom, diagnosis commands, one or more real fixes and
several plausible WRONG fixes. One check decides: it must FAIL on the broken state, PASS after each fix and FAIL after each wrong fix.

Every phase starts from a brand new "world": a private copy of the package in .work/<scenario>/<phase>/pkg, its own PDFs and store.
The real package in this repository is never modified.
"""
from __future__ import annotations

import difflib
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from procutil import run_group  # noqa: E402

WORK = ROOT / ".work"
SAMPLE_DIRS = (ROOT / "samples" / "pdfs", ROOT / "scenarios" / "pdfs")
CHECKPROC = ROOT / "scenarios" / "checkproc.py"


class ScenarioError(Exception):
    """The scenario itself is wrong (an edit does not apply, a file is missing): never an outcome."""


# ---------------------------------------------------------------------------------------------------------------------
# operations: what a break, a fix or a wrong fix does to a world
# ---------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Edit:
    path: str  # relative to the package copy, for example "local_rag/ask.py"
    find: str
    replace: str

    def describe(self) -> str:
        diff = difflib.unified_diff(self.find.splitlines(), self.replace.splitlines(), lineterm="", n=0)
        body = [l for l in diff if not l.startswith(("---", "+++", "@@"))]
        return f"edit {self.path}\n" + "\n".join("    " + l for l in body)


@dataclass(frozen=True)
class Env:
    key: str  # without the LOCAL_RAG_ prefix, for example "K"
    value: str | None  # None removes it

    def describe(self) -> str:
        return f"unset LOCAL_RAG_{self.key}" if self.value is None else f"set LOCAL_RAG_{self.key}={self.value}"


@dataclass(frozen=True)
class Cli:
    args: tuple[str, ...]
    note: str = ""

    def describe(self) -> str:
        return "run: python -m local_rag " + " ".join(self.args)


@dataclass(frozen=True)
class RmStore:
    def describe(self) -> str:
        return "delete the store folder"


@dataclass(frozen=True)
class Rm:
    path: str  # relative to the world folder, for example "store/meta.json"

    def describe(self) -> str:
        return f"delete {self.path}"


def cli(*args: str, note: str = "") -> Cli:
    return Cli(tuple(args), note)


Op = Edit | Env | Cli | RmStore | Rm
OpsOrFactory = "list[Op] | Callable[[str], list[Op]]"


@dataclass
class Scenario:
    name: str
    title: str
    story: str  # what happened, in two or three sentences
    pdfs: list[str]  # file names from samples/pdfs or scenarios/pdfs, copied into the world's pdfs/ folder
    setup: list[Op]  # builds the healthy state before the break (usually an ingest)
    break_: list[Op]  # what goes wrong
    symptom: list[Cli]  # commands whose real output is the symptom (run in the broken state)
    diagnose: list[Cli]  # commands that locate the cause
    check: Callable  # check(ctx): the verdict, see checkproc.Ctx
    fixes: dict[str, list[Op]]
    wrongs: dict[str, list[Op]]
    fix_notes: dict[str, str] = field(default_factory=dict)
    wrong_notes: dict[str, str] = field(default_factory=dict)
    observe: list[Cli] = field(default_factory=list)  # run after the check in the broken and in the first fixed state; shown, never gating
    live_only: bool = False  # needs the real Ollama: skipped with the fake backend
    env: dict[str, dict[str, str]] = field(default_factory=dict)  # per backend: extra settings for every phase, {"fake": {...}, "ollama": {...}}
    backend_ops: Callable[[str], dict[str, list[Op]]] | None = None  # ops that differ per backend: returns {"break": [...], "fixes": ..., }


# ---------------------------------------------------------------------------------------------------------------------
# the world
# ---------------------------------------------------------------------------------------------------------------------
BASE_ENV = {
    "fake": {"LOCAL_RAG_EMBEDDER": "fake", "LOCAL_RAG_LLM": "fake", "LOCAL_RAG_MIN_SCORE": "0.30"},
    "ollama": {},
}


class World:
    def __init__(self, scenario: Scenario, backend: str, phase: str):
        self.scenario, self.backend, self.phase = scenario, backend, phase
        self.dir = WORK / scenario.name / f"{backend}-{phase}"
        if self.dir.exists():
            shutil.rmtree(self.dir)
        (self.dir / "pkg").mkdir(parents=True)
        shutil.copytree(ROOT / "local_rag", self.dir / "pkg" / "local_rag", ignore=shutil.ignore_patterns("__pycache__"))
        (self.dir / "pdfs").mkdir()
        for name in scenario.pdfs:
            src = next((d / name for d in SAMPLE_DIRS if (d / name).exists()), None)
            if src is None:
                raise ScenarioError(f"{scenario.name}: PDF '{name}' not found in samples/pdfs or scenarios/pdfs")
            shutil.copy(src, self.dir / "pdfs" / name)
        self.env: dict[str, str] = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "PYTHONPATH": str(self.dir / "pkg"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LOCAL_RAG_STORE_DIR": "store",
            "NO_COLOR": "1",
            **BASE_ENV[backend],
            **scenario.env.get(backend, {}),
        }
        for key in ("LOCAL_RAG_OLLAMA_HOST",):
            if key in os.environ:
                self.env[key] = os.environ[key]
        self.log: list[str] = []

    # ---- running things inside the world --------------------------------------------------------------------------
    def python(self, args: list[str], timeout: float = 300.0):
        return run_group([sys.executable, "-B", *args], cwd=str(self.dir), env=self.env, timeout=timeout)

    def run_cli(self, args: tuple[str, ...], timeout: float = 300.0):
        return self.python(["-m", "local_rag", *args], timeout)

    def check(self, timeout: float = 600.0):
        return run_group([sys.executable, "-B", str(CHECKPROC), self.scenario.name, self.backend], cwd=str(self.dir), env=self.env, timeout=timeout)

    # ---- applying operations --------------------------------------------------------------------------------------
    def apply(self, ops: list[Op]) -> list[tuple[Op, str]]:
        done: list[tuple[Op, str]] = []
        for op in ops:
            out = ""
            if isinstance(op, Edit):
                target = self.dir / "pkg" / op.path
                if not target.exists():
                    raise ScenarioError(f"{self.scenario.name}: {op.path} does not exist in the package copy")
                text = target.read_text(encoding="utf-8")
                n = text.count(op.find)
                if n != 1:
                    raise ScenarioError(f"{self.scenario.name}: edit of {op.path} does not apply (the text occurs {n} times, must be once): {op.find[:80]!r}")
                target.write_text(text.replace(op.find, op.replace), encoding="utf-8")
            elif isinstance(op, Env):
                full = "LOCAL_RAG_" + op.key
                if op.value is None:
                    self.env.pop(full, None)
                else:
                    self.env[full] = op.value
            elif isinstance(op, Cli):
                res = self.run_cli(op.args)
                out = res.output
                if res.timed_out:
                    raise ScenarioError(f"{self.scenario.name}: command timed out: {op.describe()}")
            elif isinstance(op, RmStore):
                shutil.rmtree(self.dir / "store", ignore_errors=True)
            elif isinstance(op, Rm):
                (self.dir / op.path).unlink()
            else:  # pragma: no cover
                raise ScenarioError(f"unknown op {op!r}")
            done.append((op, out))
        return done

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


# ---------------------------------------------------------------------------------------------------------------------
# redaction: recorded output must not carry this machine's paths
# ---------------------------------------------------------------------------------------------------------------------
def redact(text: str, world: World | None = None) -> str:
    if world is not None:
        text = text.replace(str(world.dir.resolve()), "<world>").replace(str(world.dir), "<world>")
    text = text.replace(str(ROOT.resolve()), "<repo>").replace(str(ROOT), "<repo>")
    home = os.environ.get("HOME", "")
    if home:
        text = text.replace(home, "~")
    text = re.sub(r"/private/var/folders/[^\s'\"]+", "<tmp>", text)
    text = re.sub(r"\b\d+\.\d{2,} ?s\b", "<t>s", text)
    return text.rstrip()


# ---------------------------------------------------------------------------------------------------------------------
# running a scenario
# ---------------------------------------------------------------------------------------------------------------------
@dataclass
class Phase:
    name: str
    passed: bool | None = None  # the check's verdict
    check_output: str = ""
    ops: list[tuple[Op, str]] = field(default_factory=list)
    observed: list[tuple[str, str]] = field(default_factory=list)
    seconds: float = 0.0


@dataclass
class Outcome:
    scenario: Scenario
    backend: str
    skipped: str = ""
    control: Phase | None = None
    broken: Phase | None = None
    symptom: list[tuple[str, str]] = field(default_factory=list)
    diagnose: list[tuple[str, str]] = field(default_factory=list)
    fixes: dict[str, Phase] = field(default_factory=dict)
    wrongs: dict[str, Phase] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.skipped and not self.problems


def _ops(spec, backend: str) -> list[Op]:
    return spec(backend) if callable(spec) else list(spec)


def _build(scenario: Scenario, backend: str, phase: str, steps: list) -> tuple[World, Phase]:
    world = World(scenario, backend, phase)
    ph = Phase(phase)
    started = time.time()
    for step in steps:
        ph.ops.extend((op, redact(out, world)) for op, out in world.apply(_ops(step, backend)))
    ph.seconds = time.time() - started
    return world, ph


def _verdict(world: World, ph: Phase) -> None:
    res = world.check()
    ph.passed = (res.returncode == 0) and not res.timed_out
    ph.check_output = redact(res.output + ("\n(check timed out)" if res.timed_out else ""), world)


def _observe(world: World, cmds: list[Cli]) -> list[tuple[str, str]]:
    return [(c.describe().replace("run: ", "$ "), redact(world.run_cli(c.args).output, world)) for c in cmds]


def run_scenario(scenario: Scenario, backend: str, gate: Callable[[str], None] | None = None, keep: bool = False) -> Outcome:
    out = Outcome(scenario, backend)
    if scenario.live_only and backend != "ollama":
        out.skipped = "needs the real Ollama"
        return out
    pre = [scenario.setup]
    brk = pre + [scenario.break_]
    worlds: list[World] = []

    def phase(name: str, steps: list) -> tuple[World, Phase]:
        if gate:
            gate(f"{scenario.name}/{name}")
        w, p = _build(scenario, backend, name, steps)
        worlds.append(w)
        return w, p

    try:
        # 1. control: the healthy state passes the check (the check is not simply always red)
        w, out.control = phase("control", pre)
        _verdict(w, out.control)
        if out.control.passed is not True:
            out.problems.append("control: the healthy state does not pass the check")
        # 2. broken: the check fails; capture the real symptom and the diagnosis
        w, out.broken = phase("broken", brk)
        _verdict(w, out.broken)
        if out.broken.passed is not False:
            out.problems.append("broken: the check does not fail on the broken state")
        out.symptom = _observe(w, scenario.symptom)
        out.diagnose = _observe(w, scenario.diagnose)
        out.broken.observed = _observe(w, scenario.observe)
        # 3. fixes
        for i, (name, ops) in enumerate(scenario.fixes.items()):
            w, ph = phase(f"fix-{name}", brk + [ops])
            _verdict(w, ph)
            if ph.passed is not True:
                out.problems.append(f"fix '{name}' does not pass the check")
            if i == 0:
                ph.observed = _observe(w, scenario.observe)
            out.fixes[name] = ph
        # 4. wrong fixes
        for name, ops in scenario.wrongs.items():
            w, ph = phase(f"wrong-{name}", brk + [ops])
            _verdict(w, ph)
            if ph.passed is not False:
                out.problems.append(f"wrong fix '{name}' is ACCEPTED by the check")
            out.wrongs[name] = ph
        if len(scenario.wrongs) < 2:
            out.problems.append("fewer than 2 wrong fixes")
    finally:
        if not keep:
            for w in worlds:
                w.cleanup()
    return out


def load_scenarios() -> list[Scenario]:
    import importlib

    sys.path.insert(0, str(ROOT / "scenarios"))
    names = sorted(p.stem for p in (ROOT / "scenarios" / "defs").glob("s[0-9][0-9]_*.py"))
    return [importlib.import_module(f"defs.{n}").SCENARIO for n in names]
