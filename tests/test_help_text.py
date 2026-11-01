"""Every command line parses its own --help. argparse formats help text with %-codes, so a bare "35% memory" in a help string
raises ValueError: on Python 3.14 as soon as the argument is added, on older versions only when --help is asked for."""
from __future__ import annotations

import subprocess
import sys

import pytest

from .conftest import ROOT

pytestmark = pytest.mark.tooling

COMMANDS = {
    "run_eval": [sys.executable, str(ROOT / "scripts" / "run_eval.py"), "--help"],
    "mutation_check": [sys.executable, str(ROOT / "scripts" / "mutation_check.py"), "--help"],
    "cli": [sys.executable, "-m", "local_rag", "--help"],
}


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_help_prints_usage_and_exits_zero(name):
    done = subprocess.run(COMMANDS[name], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr[-400:]
    assert "usage:" in done.stdout.lower()
    assert "badly formed" not in done.stderr
