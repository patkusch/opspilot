"""In-memory state for the demo — resets on restart, which is exactly what you
want for a repeatable hackathon run."""
from __future__ import annotations

from datetime import datetime, timezone
from .domain import AuditEvent, Break, Plan, RunResult
from .seed import seed_breaks
from . import engine


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.breaks: list[Break] = seed_breaks()
        self.audit: list[AuditEvent] = [
            AuditEvent(ts=_now(), actor="agent", action="queue.loaded",
                       detail=f"Loaded {len(self.breaks)} open reconciliation breaks "
                              f"(£{engine.ledger_open_total(self.breaks):,.0f} unreconciled).")
        ]

    def plan(self, intent: str) -> Plan:
        p = engine.build_plan(intent, self.breaks)
        self.audit.append(AuditEvent(
            ts=_now(), actor="agent", action="intent.parsed",
            detail=f'"{intent}" → {p.summary["matched_items"]} match, '
                   f'{p.summary["writeoff_items"]} write-off, {p.summary["escalated_items"]} escalate (preview only)',
        ))
        return p

    def run(self, intent: str, operator: str) -> RunResult:
        name = operator.strip()
        if not name:
            raise ValueError("A named operator is required to run the agent.")
        if name.lower() == "agent":
            raise ValueError("The agent cannot authorise its own run — a human must.")

        plan = engine.build_plan(intent, self.breaks)
        result = engine.execute_and_verify(plan, self.breaks, name)

        self.audit.append(AuditEvent(
            ts=_now(), actor=name, action="run.executed",
            detail=result.summary,
        ))
        for d in result.escalated:
            self.audit.append(AuditEvent(
                ts=_now(), actor="agent", action="break.escalated",
                detail=f"{d.break_id} (£{d.amount_gbp:,.0f}) → human: {d.reason}",
            ))
        return result

    def state(self) -> dict:
        return {
            "breaks": [b.model_dump() for b in self.breaks],
            "ledger_open_gbp": engine.ledger_open_total(self.breaks),
            "open_count": len([b for b in self.breaks if b.status == "open"]),
            "guardrails": {
                "dual_control_limit": engine.DUAL_CONTROL_LIMIT,
                "write_off_limit": engine.WRITE_OFF_LIMIT,
                "write_off_min_age": engine.WRITE_OFF_MIN_AGE,
                "batch_write_off_cap": engine.BATCH_WRITE_OFF_CAP,
            },
            "audit": [a.model_dump() for a in reversed(self.audit)],
        }


STORE = Store()
