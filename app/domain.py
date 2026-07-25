"""Domain models for OpsPilot — an agentic back-office ops copilot.

The vocabulary is deliberately close to how a bank's reconciliation / exceptions
team actually talks: breaks, offsets, write-offs, dual control, escalation.
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel

BreakType = Literal["duplicate", "timing", "fx", "missing"]
Currency = Literal["GBP", "EUR", "USD"]
BreakStatus = Literal["open", "cleared", "escalated"]
Action = Literal["auto_match", "write_off", "escalate"]


class Break(BaseModel):
    id: str
    account: str
    break_type: BreakType
    currency: Currency
    amount_gbp: float          # normalised to GBP for guardrail comparisons
    age_days: int
    counterparty: str
    has_offset: bool           # a matching offsetting entry exists (enables auto-match)
    status: BreakStatus = "open"
    cleared_by: Optional[str] = None  # "agent" or a human name


class Disposition(BaseModel):
    """What the agent proposes to do with one break — and whether it's allowed to."""
    break_id: str
    amount_gbp: float
    action: Action
    eligible: bool             # may the agent execute this automatically?
    requires_human: bool       # forced to a human (dual control / not eligible)
    reason: str


class Plan(BaseModel):
    intent: str
    parsed: dict               # the structured reading of the natural-language intent
    dispositions: list[Disposition]
    summary: dict              # counts + value, pre-execution


class VerificationCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class RunResult(BaseModel):
    ok: bool
    operator: str
    executed: list[Disposition]
    escalated: list[Disposition]
    verification: list[VerificationCheck]
    ledger_before: float
    ledger_after: float
    reconciled_gbp: float
    summary: str


class AuditEvent(BaseModel):
    ts: str
    actor: str                 # "agent" or a human name
    action: str
    detail: str
