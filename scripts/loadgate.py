"""Wait until the machine is calm before a heavy command: 1-minute load average below 6 and at least 35 percent of the memory free.

Free memory is the "System-wide memory free percentage" that macOS `memory_pressure` prints. Swap used (`sysctl vm.swapusage`) is
deliberately NOT part of the rule: macOS keeps the swap figure high long after the pressure that caused it is gone, so it says
little about whether the machine can take a job now.

Gives up (raises Overloaded) after 20 minutes instead of running on a loaded machine.

Two levels, on purpose:
  wait_for_calm     the rule above, checked once before a heavy job starts
  wait_between      a looser pause (load < 10, at least 20 percent free) between the items of a job that is already running. A job that
                    loads two models takes about 20 points of free memory by itself, so asking for 35 percent before every single question
                    would make the job wait for a state that its own first request has just ended. The pause still stops it from piling on
                    when the rest of the machine becomes very busy.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time

MAX_LOAD = 6.0
MIN_FREE_PERCENT = 35.0
BETWEEN_MAX_LOAD = 10.0
BETWEEN_MIN_FREE_PERCENT = 20.0
POLL_SECONDS = 30
MAX_WAIT_MINUTES = 20


class Overloaded(RuntimeError):
    pass


def free_memory_percent() -> float | None:
    """macOS only (`memory_pressure`). None where it cannot be read, and then only the load average is checked."""
    try:
        out = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"System-wide memory free percentage:\s*([0-9.]+)%", out)
    return float(m.group(1)) if m else None


def calm(max_load: float = MAX_LOAD, min_free_percent: float = MIN_FREE_PERCENT) -> tuple[bool, float, float | None]:
    load = os.getloadavg()[0]
    free = free_memory_percent()
    return load < max_load and (free is None or free >= min_free_percent), load, free


def wait_for_calm(label: str, max_load: float = MAX_LOAD, min_free_percent: float = MIN_FREE_PERCENT, poll: float = POLL_SECONDS, max_wait_minutes: float = MAX_WAIT_MINUTES) -> None:
    deadline = time.time() + max_wait_minutes * 60
    announced = False
    while True:
        ok, load, free = calm(max_load, min_free_percent)
        if ok:
            return
        if time.time() >= deadline:
            raise Overloaded(f"load {load:.1f} / free memory {free}% stayed outside the limits (load < {max_load}, free memory >= {min_free_percent}%) for {max_wait_minutes} minutes before {label}; giving up instead of running on a loaded machine.")
        if not announced:
            print(f"waiting for the machine to calm down before {label} (load {load:.1f}, free memory {free}%; need load < {max_load} and free memory >= {min_free_percent}%)...", file=sys.stderr, flush=True)
            announced = True
        time.sleep(poll)


def wait_between(label: str, poll: float = POLL_SECONDS, max_wait_minutes: float = MAX_WAIT_MINUTES) -> None:
    """The pause between the items of a job that has already started (see the top of this file)."""
    wait_for_calm(label, BETWEEN_MAX_LOAD, BETWEEN_MIN_FREE_PERCENT, poll, max_wait_minutes)
