"""Run a command in its own process group with a hard timeout, and make sure nothing of it is left running."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass


@dataclass
class RunResult:
    returncode: int | None  # None when the process was killed after the timeout
    output: str  # stdout and stderr together
    timed_out: bool
    leftover: bool  # True if some process of the group was still alive after the kill (must never happen)
    seconds: float


def group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def reap_group(pgid: int) -> bool:
    """Kill whatever is left in the group and confirm it is gone. Returns True when nothing survives."""
    kill_group(pgid)
    for _ in range(50):
        if not group_alive(pgid):
            return True
        time.sleep(0.1)
        kill_group(pgid)
    return not group_alive(pgid)


def run_group(argv: list[str], *, cwd: str, env: dict[str, str], timeout: float, stdin: str | None = None) -> RunResult:
    started = time.time()
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL if stdin is None else subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,  # its own process group: the timeout kills the process and everything it started
    )
    timed_out = False
    try:
        out, _ = proc.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_group(proc.pid)
        try:
            out, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            out = ""
    gone = reap_group(proc.pid)
    return RunResult(None if timed_out else proc.returncode, out or "", timed_out, not gone, time.time() - started)
