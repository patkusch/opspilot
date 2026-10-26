"""The web layer: what a caller of the API sees, without starting a server.

The handlers are plain functions, so they are called directly. The checks that the
agent obeys its limits live in test_guardrails.py; this file checks that the API
hands those answers back correctly.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import main
from app.store import STORE


@pytest.fixture(autouse=True)
def clean_store():
    STORE.reset()
    yield
    STORE.reset()


def test_state_lists_the_open_breaks_the_guardrail_limits_and_the_audit_trail():
    s = main.get_state()
    assert s["open_count"] == len(s["breaks"]) > 0
    assert set(s["guardrails"]) == {"dual_control_limit", "write_off_limit", "write_off_min_age", "batch_write_off_cap"}
    assert s["audit"][0]["action"] == "queue.loaded"


def test_a_plan_is_only_a_preview_and_changes_nothing():
    before = main.get_state()
    plan = main.post_plan(main.PlanReq(intent="write off the small old items"))
    after = main.get_state()
    assert isinstance(plan, dict) and "summary" in plan
    assert [b["status"] for b in after["breaks"]] == [b["status"] for b in before["breaks"]]
    assert after["audit"][0]["action"] == "intent.parsed"


def test_a_run_with_no_operator_name_is_refused_with_a_400_and_changes_nothing():
    with pytest.raises(HTTPException) as e:
        main.post_run(main.RunReq(intent="match everything", operator="  "))
    assert e.value.status_code == 400
    assert "operator" in e.value.detail.lower()
    assert all(b["status"] == "open" for b in main.get_state()["breaks"])


def test_the_agent_cannot_name_itself_as_the_operator_through_the_api_either():
    with pytest.raises(HTTPException) as e:
        main.post_run(main.RunReq(intent="match everything", operator="agent"))
    assert e.value.status_code == 400
    assert "own run" in e.value.detail


def test_a_run_by_a_named_person_is_recorded_in_the_audit_trail():
    result = main.post_run(main.RunReq(intent="match everything", operator="Priya"))
    assert isinstance(result, dict)
    assert any(a["actor"] == "Priya" and a["action"] == "run.executed" for a in main.get_state()["audit"])


def test_reset_puts_the_queue_and_the_trail_back_as_they_started():
    main.post_run(main.RunReq(intent="match everything", operator="Priya"))
    assert main.post_reset() == {"ok": True}
    s = main.get_state()
    assert all(b["status"] == "open" for b in s["breaks"])
    assert [a["action"] for a in s["audit"]] == ["queue.loaded"]
