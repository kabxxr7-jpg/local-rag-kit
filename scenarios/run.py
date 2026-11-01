#!/usr/bin/env python
"""Run the "fix an inherited pipeline" scenarios.

    python scenarios/run.py                        every scenario that can run offline (fake embedder, fake model)
    python scenarios/run.py --backend ollama       every scenario against the real Ollama (one request at a time, load gate on)
    python scenarios/run.py --only duplicate-chunks,table-flattened
    python scenarios/run.py --list
    python scenarios/run.py --backend ollama --record     also (re)write docs/scenarios/*.md and docs/SCENARIOS.md from this run

Exit code 0 only if, for every scenario: the healthy state passes the check, the broken state fails it, every fix passes it
and every wrong fix is refused by it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

import framework  # noqa: E402
from report import write_reports  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["fake", "ollama"], default="fake")
    ap.add_argument("--only", help="comma separated scenario names")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--record", action="store_true", help="write docs/scenarios from this run (use with --backend ollama)")
    ap.add_argument("--keep", action="store_true", help="keep .work/ folders")
    ap.add_argument("--no-gate", action="store_true", help="do not wait for a calm machine (fake backend only)")
    args = ap.parse_args()

    scenarios = framework.load_scenarios()
    if args.list:
        for s in scenarios:
            print(f"{s.name:34} {'live only' if s.live_only else 'offline+live':13} fixes={len(s.fixes)} wrong={len(s.wrongs)}  {s.title}")
        return 0
    if args.only:
        wanted = set(args.only.split(","))
        unknown = wanted - {s.name for s in scenarios}
        if unknown:
            print("unknown scenario(s): " + ", ".join(sorted(unknown)), file=sys.stderr)
            return 2
        scenarios = [s for s in scenarios if s.name in wanted]

    gate = None
    if args.backend == "ollama" or not args.no_gate:
        import loadgate

        def gate(label: str) -> None:  # noqa: F811
            if args.backend == "ollama":
                loadgate.wait_for_calm(label)

    outcomes = []
    for s in scenarios:
        print(f"== {s.name} ({args.backend})", flush=True)
        o = framework.run_scenario(s, args.backend, gate=gate, keep=args.keep)
        outcomes.append(o)
        if o.skipped:
            print(f"   skipped: {o.skipped}")
            continue
        print(f"   control {'passes' if o.control.passed else 'FAILS'}; broken {'fails' if o.broken.passed is False else 'PASSES'}; "
              f"fixes {sum(1 for p in o.fixes.values() if p.passed)}/{len(o.fixes)} pass; wrong fixes {sum(1 for p in o.wrongs.values() if p.passed is False)}/{len(o.wrongs)} refused")
        for p in o.problems:
            print(f"   PROBLEM: {p}")
    ran = [o for o in outcomes if not o.skipped]
    bad = [o for o in ran if not o.ok]
    print(f"\n{len(ran)} scenario(s) run, {len(outcomes) - len(ran)} skipped, {len(bad)} with problems")
    print(f"fixes passing: {sum(sum(1 for p in o.fixes.values() if p.passed) for o in ran)}/{sum(len(o.fixes) for o in ran)}; "
          f"wrong fixes refused: {sum(sum(1 for p in o.wrongs.values() if p.passed is False) for o in ran)}/{sum(len(o.wrongs) for o in ran)}")
    if args.record:
        write_reports(outcomes, args.backend)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
