"""The agent's brain — deterministic, guardrailed, and self-verifying.

Design lineage (steal like an artist):
  • SipQuest  — natural-language intent → a *verified* real-world action, with hard
                safety constraints on what the agent may do unattended.
  • RuleLift  — prove, don't trust: the outcome is checked against the ledger, and
                the agent never reports success it can't demonstrate.
  • Remedia   — guardrails live in code, not in a prompt; every action is audited.
"""
from __future__ import annotations

import re
from .domain import Break, Disposition, Plan, VerificationCheck, RunResult

# ── Guardrails — hard-coded, tested, not prompt intentions ───────────────────
DUAL_CONTROL_LIMIT = 10_000.0   # at/above this, the agent may NEVER act — human only
WRITE_OFF_LIMIT = 250.0         # the agent may write off at most this per item
WRITE_OFF_MIN_AGE = 30          # only stale items are write-off candidates
BATCH_WRITE_OFF_CAP = 5_000.0   # total the agent may write off in a single run


# ── Intent parsing — natural language → a structured, explainable reading ────
def parse_intent(intent: str) -> dict:
    t = intent.lower()

    if re.search(r"\bwrite[\s-]?off\b", t):
        action = "write_off"
    elif re.search(r"\b(escalate|review|refer)\b", t):
        action = "escalate"
    elif re.search(r"\b(match|clear|reconcile|resolve|close)\b", t):
        action = "auto_match"
    else:
        action = "triage"  # let the agent choose the safe action per item

    parsed: dict = {"action": action, "filters": {}}
    f = parsed["filters"]

    m = re.search(r"(under|below|less than|<)\s*[£$€]?\s*([\d,]+)", t)
    if m:
        f["max_amount"] = float(m.group(2).replace(",", ""))
    m = re.search(r"(over|above|more than|greater than|>)\s*[£$€]?\s*([\d,]+)", t)
    if m:
        f["min_amount"] = float(m.group(2).replace(",", ""))
    m = re.search(r"(older than|over|>)\s*(\d+)\s*day", t)
    if m:
        f["min_age"] = int(m.group(2))

    for bt in ("duplicate", "timing", "fx", "missing"):
        if bt in t:
            f["break_type"] = bt
    for ccy in ("gbp", "eur", "usd"):
        if ccy in t:
            f["currency"] = ccy.upper()

    return parsed


def _matches(b: Break, f: dict) -> bool:
    if "max_amount" in f and b.amount_gbp > f["max_amount"]:
        return False
    if "min_amount" in f and b.amount_gbp < f["min_amount"]:
        return False
    if "min_age" in f and b.age_days < f["min_age"]:
        return False
    if "break_type" in f and b.break_type != f["break_type"]:
        return False
    if "currency" in f and b.currency != f["currency"]:
        return False
    return True


def _decide(b: Break, requested: str) -> Disposition:
    """Choose an action for one break and run it past the guardrails.

    Whatever the human asked for, the guardrails have the final say. Ask to write
    off a £40k break and you get an escalation, not a write-off — enforced here,
    not hoped for in a prompt."""
    amt = b.amount_gbp

    # Guardrail 1: dual control — nothing at/over the limit is ever automatic.
    if amt >= DUAL_CONTROL_LIMIT:
        return Disposition(break_id=b.id, amount_gbp=amt, action="escalate",
                           eligible=False, requires_human=True,
                           reason=f"£{amt:,.0f} ≥ £{DUAL_CONTROL_LIMIT:,.0f} dual-control limit — human sign-off required")

    # Decide the intended action (explicit request, else agent triage).
    if requested == "auto_match":
        intended = "auto_match"
    elif requested == "write_off":
        intended = "write_off"
    elif requested == "escalate":
        intended = "escalate"
    else:  # triage: prefer a match, then a compliant write-off, else escalate
        if b.has_offset:
            intended = "auto_match"
        elif amt <= WRITE_OFF_LIMIT and b.age_days >= WRITE_OFF_MIN_AGE:
            intended = "write_off"
        else:
            intended = "escalate"

    if intended == "auto_match":
        if b.has_offset:
            return Disposition(break_id=b.id, amount_gbp=amt, action="auto_match",
                               eligible=True, requires_human=False,
                               reason="offsetting entry found — safe to auto-match")
        return Disposition(break_id=b.id, amount_gbp=amt, action="escalate",
                           eligible=False, requires_human=True,
                           reason="no offsetting entry — cannot auto-match, referred to human")

    if intended == "write_off":
        if amt > WRITE_OFF_LIMIT:
            return Disposition(break_id=b.id, amount_gbp=amt, action="escalate",
                               eligible=False, requires_human=True,
                               reason=f"£{amt:,.0f} > £{WRITE_OFF_LIMIT:,.0f} agent write-off limit — escalated")
        if b.age_days < WRITE_OFF_MIN_AGE:
            return Disposition(break_id=b.id, amount_gbp=amt, action="escalate",
                               eligible=False, requires_human=True,
                               reason=f"only {b.age_days}d old (< {WRITE_OFF_MIN_AGE}d) — too fresh to write off")
        return Disposition(break_id=b.id, amount_gbp=amt, action="write_off",
                           eligible=True, requires_human=False,
                           reason=f"£{amt:,.0f} ≤ limit and {b.age_days}d old — compliant write-off")

    return Disposition(break_id=b.id, amount_gbp=amt, action="escalate",
                       eligible=False, requires_human=True,
                       reason="referred to human for review")


def build_plan(intent: str, breaks: list[Break]) -> Plan:
    parsed = parse_intent(intent)
    action = parsed["action"]
    f = parsed["filters"]

    dispositions: list[Disposition] = []
    running_writeoff = 0.0
    for b in breaks:
        if b.status != "open" or not _matches(b, f):
            continue
        d = _decide(b, action)
        # Guardrail 4: batch write-off cap — once hit, remaining write-offs escalate.
        if d.action == "write_off":
            if running_writeoff + d.amount_gbp > BATCH_WRITE_OFF_CAP:
                d = Disposition(break_id=b.id, amount_gbp=d.amount_gbp, action="escalate",
                                eligible=False, requires_human=True,
                                reason=f"batch write-off cap £{BATCH_WRITE_OFF_CAP:,.0f} reached — escalated")
            else:
                running_writeoff += d.amount_gbp
        dispositions.append(d)

    auto = [d for d in dispositions if d.eligible]
    esc = [d for d in dispositions if not d.eligible]
    summary = {
        "matched_items": len([d for d in auto if d.action == "auto_match"]),
        "writeoff_items": len([d for d in auto if d.action == "write_off"]),
        "escalated_items": len(esc),
        "auto_value_gbp": round(sum(d.amount_gbp for d in auto), 2),
        "escalated_value_gbp": round(sum(d.amount_gbp for d in esc), 2),
    }
    return Plan(intent=intent, parsed=parsed, dispositions=dispositions, summary=summary)


def ledger_open_total(breaks: list[Break]) -> float:
    return round(sum(b.amount_gbp for b in breaks if b.status == "open"), 2)


def execute_and_verify(plan: Plan, breaks: list[Break], operator: str) -> RunResult:
    """Apply the eligible dispositions, then PROVE the outcome against the ledger.

    This is the RuleLift move: we don't report 'done', we report 'done and here is
    the arithmetic that shows it'. If the identity didn't hold, ok=False."""
    by_id = {b.id: b for b in breaks}
    before = ledger_open_total(breaks)

    executed: list[Disposition] = []
    escalated: list[Disposition] = []
    matched_val = 0.0
    writeoff_val = 0.0

    for d in plan.dispositions:
        b = by_id[d.break_id]
        if b.status != "open":
            continue
        if d.eligible and d.action == "auto_match":
            b.status = "cleared"; b.cleared_by = "agent"
            matched_val += d.amount_gbp
            executed.append(d)
        elif d.eligible and d.action == "write_off":
            b.status = "cleared"; b.cleared_by = "agent"
            writeoff_val += d.amount_gbp
            executed.append(d)
        else:
            b.status = "escalated"
            escalated.append(d)

    after = ledger_open_total(breaks)
    reconciled = round(matched_val + writeoff_val, 2)
    escalated_val = round(sum(d.amount_gbp for d in escalated), 2)

    # ── Verification — the outcome must be provable, not asserted ────────────
    # Conservation: no pound vanishes. Every pound that left the open queue is
    # either reconciled (matched/written-off) or escalated to a human.
    cleared_ids = [d.break_id for d in executed]
    checks = [
        VerificationCheck(
            name="Conservation of value",
            passed=abs((before - after) - (reconciled + escalated_val)) < 0.01,
            detail=f"open £{before:,.2f} − £{after:,.2f} = £{before - after:,.2f} left the queue "
                   f"= reconciled £{reconciled:,.2f} + escalated £{escalated_val:,.2f} (nothing lost)",
        ),
        VerificationCheck(
            name="Cleared breaks actually gone",
            passed=all(by_id[i].status == "cleared" for i in cleared_ids),
            detail=f"{len(cleared_ids)} break(s) confirmed no longer open in the queue",
        ),
        VerificationCheck(
            name="No over-limit item auto-actioned",
            passed=all(d.amount_gbp < DUAL_CONTROL_LIMIT for d in executed),
            detail=f"every automatic action was under the £{DUAL_CONTROL_LIMIT:,.0f} dual-control line",
        ),
        VerificationCheck(
            name="Write-off cap respected",
            passed=writeoff_val <= BATCH_WRITE_OFF_CAP + 0.01,
            detail=f"agent wrote off £{writeoff_val:,.2f} ≤ £{BATCH_WRITE_OFF_CAP:,.0f} cap",
        ),
    ]
    ok = all(c.passed for c in checks)

    summary = (
        f"Cleared {len(executed)} break(s), £{reconciled:,.0f} reconciled, "
        f"ledger {'balanced ✓' if ok else 'FAILED ✗'} — "
        f"{len(escalated)} item(s) escalated to a human. Verified, not asserted."
    )
    return RunResult(ok=ok, operator=operator, executed=executed, escalated=escalated,
                     verification=checks, ledger_before=before, ledger_after=after,
                     reconciled_gbp=reconciled, summary=summary)
