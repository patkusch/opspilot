"""The guardrails, tested — because the engine's own header says they are.

Each guardrail in the README table gets a test that tries to break it from the
outside: ask for the forbidden thing and check the code refuses. The
verification model is tested the same way, by handing it a plan the planner
would never produce and checking it fails the run rather than trusting it.
"""
from __future__ import annotations

import pytest

from app import engine
from app.domain import Break, Disposition, Plan
from app.engine import (
    BATCH_WRITE_OFF_CAP,
    DUAL_CONTROL_LIMIT,
    WRITE_OFF_LIMIT,
    WRITE_OFF_MIN_AGE,
    build_plan,
    execute_and_verify,
    parse_intent,
)
from app.seed import seed_breaks
from app.store import Store


def brk(id: str, amount: float, *, age: int = 60, offset: bool = False,
        break_type: str = "timing", currency: str = "GBP") -> Break:
    return Break(id=id, account="NOSTRO-GBP-01", break_type=break_type, currency=currency,
                 amount_gbp=amount, age_days=age, counterparty="Test", has_offset=offset)


def one(intent: str, b: Break) -> Disposition:
    plan = build_plan(intent, [b])
    assert len(plan.dispositions) == 1
    return plan.dispositions[0]


# ── Guardrail 1: dual control ───────────────────────────────────────────────

class TestDualControl:
    def test_at_the_limit_is_human_only_whatever_was_asked(self):
        for intent in ("write off everything", "match everything", "escalate everything", "sort out the queue"):
            d = one(intent, brk("b", DUAL_CONTROL_LIMIT, offset=True))
            assert d.action == "escalate" and d.requires_human and not d.eligible, intent
            assert "dual-control" in d.reason

    def test_just_under_the_limit_may_be_matched_with_an_offset(self):
        d = one("match everything", brk("b", DUAL_CONTROL_LIMIT - 0.01, offset=True))
        assert d.action == "auto_match" and d.eligible

    def test_forty_thousand_pound_write_off_request_becomes_an_escalation(self):
        d = one("write off everything", brk("b", 40_000, age=200))
        assert d.action == "escalate" and d.requires_human


# ── Guardrail 2 and 3: write-off limit and freshness ────────────────────────

class TestWriteOff:
    def test_limit_is_inclusive(self):
        assert one("write off everything", brk("b", WRITE_OFF_LIMIT, age=WRITE_OFF_MIN_AGE)).action == "write_off"

    def test_a_penny_over_the_limit_escalates(self):
        d = one("write off everything", brk("b", WRITE_OFF_LIMIT + 0.01, age=WRITE_OFF_MIN_AGE))
        assert d.action == "escalate" and "write-off limit" in d.reason

    def test_min_age_is_inclusive_and_a_day_fresher_escalates(self):
        assert one("write off everything", brk("b", 100, age=WRITE_OFF_MIN_AGE)).action == "write_off"
        d = one("write off everything", brk("b", 100, age=WRITE_OFF_MIN_AGE - 1))
        assert d.action == "escalate" and "too fresh" in d.reason


# ── Guardrail 5: auto-match needs proof ─────────────────────────────────────

class TestAutoMatch:
    def test_no_offset_means_no_match_even_when_asked(self):
        d = one("match everything", brk("b", 100, offset=False))
        assert d.action == "escalate" and "no offsetting entry" in d.reason

    def test_triage_prefers_match_then_compliant_write_off_then_escalation(self):
        assert one("sort out the queue", brk("m", 8_000, offset=True)).action == "auto_match"
        assert one("sort out the queue", brk("w", 200, age=45)).action == "write_off"
        assert one("sort out the queue", brk("e", 200, age=5)).action == "escalate"
        assert one("sort out the queue", brk("e2", 8_000, offset=False)).action == "escalate"


# ── Guardrail 4: batch write-off cap ────────────────────────────────────────

class TestBatchCap:
    def test_write_offs_stop_at_the_cap_and_the_rest_escalate(self):
        breaks = [brk(f"b{i}", 240, age=90) for i in range(30)]  # £7,200 requested
        plan = build_plan("write off everything", breaks)
        written = [d for d in plan.dispositions if d.action == "write_off"]
        assert sum(d.amount_gbp for d in written) <= BATCH_WRITE_OFF_CAP
        assert len(written) == 20  # 20 × £240 = £4,800; the 21st would cross £5,000
        capped = [d for d in plan.dispositions if d.action == "escalate"]
        assert len(capped) == 10 and all("batch write-off cap" in d.reason for d in capped)

    def test_a_smaller_item_that_still_fits_under_the_cap_is_written_off(self):
        breaks = [brk(f"b{i}", 240, age=90) for i in range(21)] + [brk("small", 150, age=90)]
        plan = build_plan("write off everything", breaks)
        by_id = {d.break_id: d for d in plan.dispositions}
        assert by_id["b20"].action == "escalate"      # £4,800 + £240 > cap
        assert by_id["small"].action == "write_off"   # £4,800 + £150 ≤ cap


# ── Guardrail 6: no self-authorisation ──────────────────────────────────────

class TestNamedOperator:
    @pytest.mark.parametrize("operator", ["agent", "Agent", "  AGENT ", "", "   "])
    def test_the_agent_cannot_authorise_itself_and_a_blank_is_not_a_name(self, operator):
        store = Store()
        with pytest.raises(ValueError):
            store.run("match everything", operator)
        assert all(b.status == "open" for b in store.breaks), "a refused run must change nothing"

    def test_a_named_human_can_run_and_is_recorded(self):
        store = Store()
        result = store.run("match everything", "Priya Shah")
        assert result.operator == "Priya Shah"
        assert any(a.actor == "Priya Shah" and a.action == "run.executed" for a in store.audit)


# ── Guardrail 7: the outcome is proven ──────────────────────────────────────

class TestVerification:
    def test_a_seed_run_balances_and_every_check_passes(self):
        breaks = seed_breaks()
        plan = build_plan("write off everything", breaks)
        result = execute_and_verify(plan, breaks, "Priya Shah")
        assert result.ok and all(c.passed for c in result.verification)
        left = result.ledger_before - result.ledger_after
        escalated = sum(d.amount_gbp for d in result.escalated)
        assert abs(left - (result.reconciled_gbp + escalated)) < 0.01
        assert all(b.status != "open" for b in breaks if b.id in {d.break_id for d in result.executed})
        assert all(d.amount_gbp < DUAL_CONTROL_LIMIT for d in result.executed)
        assert sum(d.amount_gbp for d in result.executed if d.action == "write_off") <= BATCH_WRITE_OFF_CAP

    def test_large_breaks_in_the_seed_are_all_escalated_never_actioned(self):
        breaks = seed_breaks()
        large = {b.id for b in breaks if b.amount_gbp >= DUAL_CONTROL_LIMIT}
        assert large, "the seed is meant to include dual-control territory"
        result = execute_and_verify(build_plan("write off everything", breaks), breaks, "Priya Shah")
        assert large <= {d.break_id for d in result.escalated}
        assert not large & {d.break_id for d in result.executed}

    def test_verification_does_not_trust_the_plan(self):
        # A plan the planner would never produce: an eligible auto-match over the
        # dual-control line. Execution runs it, verification must fail the run.
        b = brk("big", 50_000, offset=True)
        rogue = Plan(intent="x", parsed={}, dispositions=[Disposition(
            break_id="big", amount_gbp=50_000, action="auto_match",
            eligible=True, requires_human=False, reason="forged")], summary={})
        result = execute_and_verify(rogue, [b], "Priya Shah")
        assert not result.ok
        failed = [c.name for c in result.verification if not c.passed]
        assert failed == ["No over-limit item auto-actioned"]
        assert "FAILED" in result.summary

    def test_a_second_run_leaves_escalated_items_with_the_human(self):
        store = Store()
        first = store.run("write off everything", "Priya Shah")
        escalated = {d.break_id for d in first.escalated}
        second = store.run("write off everything", "Priya Shah")
        assert not escalated & {d.break_id for d in second.executed}
        assert all(b.status == "escalated" for b in store.breaks if b.id in escalated)


# ── Intent parsing ──────────────────────────────────────────────────────────

class TestParseIntent:
    def test_actions(self):
        assert parse_intent("Write-off the small stuff")["action"] == "write_off"
        assert parse_intent("please match the duplicates")["action"] == "auto_match"
        assert parse_intent("refer the fx breaks")["action"] == "escalate"
        assert parse_intent("have a look at the queue")["action"] == "triage"

    def test_amount_and_age_filters_are_kept_apart(self):
        # "over 90 days" is an age, not a £90 floor.
        f = parse_intent("escalate everything over 90 days old")["filters"]
        assert f == {"min_age": 90}
        f = parse_intent("write off duplicates under £250 older than 30 days")["filters"]
        assert f == {"max_amount": 250.0, "min_age": 30, "break_type": "duplicate"}
        f = parse_intent("match anything over 1,000 in eur")["filters"]
        assert f == {"min_amount": 1000.0, "currency": "EUR"}

    def test_filters_actually_filter(self):
        breaks = [brk("old", 100, age=100), brk("new", 100, age=10), brk("eur", 100, age=100, currency="EUR")]
        plan = build_plan("write off everything over 90 days old", breaks)
        assert {d.break_id for d in plan.dispositions} == {"old", "eur"}
        plan = build_plan("write off gbp breaks", breaks)
        assert {d.break_id for d in plan.dispositions} == {"old", "new"}


def test_seed_is_deterministic():
    a, b = seed_breaks(), seed_breaks()
    assert [x.model_dump() for x in a] == [x.model_dump() for x in b]
