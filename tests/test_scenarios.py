"""The "fix an inherited pipeline" scenarios, run offline (fake embedder, fake model).

For every scenario: the healthy state passes its check, the broken state fails it, every fix passes it, every wrong fix is refused.
The two scenarios that need the real Ollama (context truncation, model not pulled) are skipped here and run by `python scenarios/run.py --backend ollama`.
"""
from __future__ import annotations

import sys

import pytest

from .conftest import ROOT

sys.path.insert(0, str(ROOT / "scenarios"))
sys.path.insert(0, str(ROOT / "scripts"))

import framework  # noqa: E402

SCENARIOS = framework.load_scenarios()
OFFLINE = [s for s in SCENARIOS if not s.live_only]


def test_the_lab_has_enough_scenarios_and_each_one_is_complete():
    assert len(SCENARIOS) >= 8
    assert len({s.name for s in SCENARIOS}) == len(SCENARIOS)
    assert len(OFFLINE) >= 8
    for s in SCENARIOS:
        assert s.fixes, s.name
        assert len(s.wrongs) >= 2, f"{s.name}: needs at least 2 wrong fixes"
        assert s.symptom and s.diagnose, s.name
        assert set(s.fixes) >= set(s.fix_notes) and set(s.wrongs) >= set(s.wrong_notes), s.name
        assert set(s.wrongs) == set(s.wrong_notes), f"{s.name}: every wrong fix needs a note saying why it is wrong"
        assert set(s.fixes) == set(s.fix_notes), f"{s.name}: every fix needs a note"
        assert not set(s.fixes) & set(s.wrongs)


def test_the_live_only_scenarios_are_exactly_the_ones_that_need_a_real_server():
    assert sorted(s.name for s in SCENARIOS if s.live_only) == ["context-truncated-num-ctx", "model-not-pulled"]


@pytest.mark.scenarios
@pytest.mark.parametrize("scenario", OFFLINE, ids=lambda s: s.name)
def test_scenario_break_fix_and_wrong_fixes(scenario):
    outcome = framework.run_scenario(scenario, "fake")
    assert outcome.control.passed is True, "the healthy state must pass the check:\n" + outcome.control.check_output
    assert outcome.broken.passed is False, "the broken state must fail the check"
    assert outcome.broken.check_output.count("FAIL") >= 1
    for name, phase in outcome.fixes.items():
        assert phase.passed is True, f"fix {name} must pass:\n{phase.check_output}"
    for name, phase in outcome.wrongs.items():
        assert phase.passed is False, f"wrong fix {name} must be refused:\n{phase.check_output}"
    assert outcome.ok, outcome.problems


def test_a_live_only_scenario_is_skipped_with_the_fake_backend():
    s = next(x for x in SCENARIOS if x.name == "model-not-pulled")
    assert framework.run_scenario(s, "fake").skipped


def test_an_edit_that_does_not_apply_is_a_scenario_error_not_a_result(tmp_path):
    s = OFFLINE[0]
    w = framework.World(s, "fake", "unit")
    try:
        with pytest.raises(framework.ScenarioError, match="does not apply"):
            w.apply([framework.Edit("local_rag/ask.py", "this text is not in the file", "x")])
        with pytest.raises(framework.ScenarioError, match="does not exist"):
            w.apply([framework.Edit("local_rag/nothing.py", "a", "b")])
    finally:
        w.cleanup()


def test_the_package_in_the_repository_is_never_touched_by_a_run():
    before = {p: p.read_bytes() for p in (ROOT / "local_rag").glob("*.py")}
    framework.run_scenario(next(x for x in OFFLINE if x.name == "duplicate-chunks"), "fake")
    assert {p: p.read_bytes() for p in (ROOT / "local_rag").glob("*.py")} == before
