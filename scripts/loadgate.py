"""Wait until the machine is calm before a heavy command: 1-minute load average below 6 and swap used below 4000 MB.

Gives up (raises Overloaded) after 20 minutes instead of running on a loaded machine.

Two levels, on purpose:
  wait_for_calm     the strict rule, checked once before a heavy job starts
  wait_between      a looser pause (load < 10, swap < 5500 MB) between the items of a job that is already running. A job that loads a
                    model raises swap itself (about 800 MB here), so asking for the strict limits before every single question would
                    make the job wait for a state that its own first request has just ended. The pause still stops it from piling on
                    when the rest of the machine becomes very busy.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time

MAX_LOAD = 6.0
MAX_SWAP_MB = 4000.0
BETWEEN_MAX_LOAD = 10.0
BETWEEN_MAX_SWAP_MB = 5500.0
POLL_SECONDS = 30
MAX_WAIT_MINUTES = 20


class Overloaded(RuntimeError):
    pass


def swap_used_mb() -> float | None:
    """macOS only (sysctl vm.swapusage). None where it cannot be read, and then only the load average is checked."""
    try:
        out = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"used = ([0-9.]+)([MG])", out)
    if not m:
        return None
    return float(m.group(1)) * (1024 if m.group(2) == "G" else 1)


def calm(max_load: float = MAX_LOAD, max_swap_mb: float = MAX_SWAP_MB) -> tuple[bool, float, float | None]:
    load = os.getloadavg()[0]
    swap = swap_used_mb()
    return load < max_load and (swap is None or swap < max_swap_mb), load, swap


def wait_for_calm(label: str, max_load: float = MAX_LOAD, max_swap_mb: float = MAX_SWAP_MB, poll: float = POLL_SECONDS, max_wait_minutes: float = MAX_WAIT_MINUTES) -> None:
    deadline = time.time() + max_wait_minutes * 60
    announced = False
    while True:
        ok, load, swap = calm(max_load, max_swap_mb)
        if ok:
            return
        if time.time() >= deadline:
            raise Overloaded(f"load {load:.1f} / swap {swap} MB stayed above the limits ({max_load} / {max_swap_mb} MB) for {max_wait_minutes} minutes before {label}; giving up instead of running on a loaded machine.")
        if not announced:
            print(f"waiting for the machine to calm down before {label} (load {load:.1f}, swap {swap if swap is None else round(swap)} MB; need load < {max_load} and swap < {max_swap_mb:.0f} MB)...", file=sys.stderr, flush=True)
            announced = True
        time.sleep(poll)


def wait_between(label: str, poll: float = POLL_SECONDS, max_wait_minutes: float = MAX_WAIT_MINUTES) -> None:
    """The pause between the items of a job that has already started (see the top of this file)."""
    wait_for_calm(label, BETWEEN_MAX_LOAD, BETWEEN_MAX_SWAP_MB, poll, max_wait_minutes)
