"""Deterministic seed data — a realistic reconciliation-breaks queue.

Reproducible on every run (fixed PRNG seed), so the demo's headline numbers are
stable and nobody can accuse it of a lucky roll.
"""
from __future__ import annotations

from .domain import Break

# Simple, dependency-free LCG so the queue is byte-identical every process start.
def _rng(seed: int):
    state = seed
    def rnd() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF
    return rnd


COUNTERPARTIES = [
    "Northwind Custody", "Aegis Payments", "Meridian Clearing", "Sterling Nominees",
    "Cirrus FX", "Blackwood Settlement", "Orion Depository", "Halcyon Markets",
    "Ferrum Bank", "Solace Cards", "Kestrel Securities", "Onyx Treasury",
]
ACCOUNTS = ["NOSTRO-GBP-01", "NOSTRO-EUR-02", "NOSTRO-USD-03", "SUSPENSE-88", "CLEARING-14"]
TYPES = ["duplicate", "timing", "fx", "missing"]
CCYS = ["GBP", "GBP", "GBP", "EUR", "USD"]  # GBP-weighted book


def seed_breaks(count: int = 60) -> list[Break]:
    rnd = _rng(424242)
    breaks: list[Break] = []
    for i in range(count):
        btype = TYPES[int(rnd() * len(TYPES))]
        ccy = CCYS[int(rnd() * len(CCYS))]

        # Amount profile: mostly small/mid, a deliberate tail of large ones that
        # must cross the dual-control line and get force-escalated.
        r = rnd()
        if r < 0.55:
            amount = round(20 + rnd() * 480, 2)        # small: many write-off eligible
        elif r < 0.9:
            amount = round(500 + rnd() * 8000, 2)       # mid
        else:
            amount = round(10000 + rnd() * 90000, 2)    # large: dual-control territory

        age = int(1 + rnd() * 120)

        # duplicates & timing breaks usually have an offsetting entry (auto-matchable);
        # fx & missing usually don't.
        offset_prob = 0.75 if btype in ("duplicate", "timing") else 0.15
        has_offset = rnd() < offset_prob

        breaks.append(Break(
            id=f"BRK-{2000 + i}",
            account=ACCOUNTS[i % len(ACCOUNTS)],
            break_type=btype,           # type: ignore[arg-type]
            currency=ccy,               # type: ignore[arg-type]
            amount_gbp=amount,
            age_days=age,
            counterparty=COUNTERPARTIES[i % len(COUNTERPARTIES)],
            has_offset=has_offset,
        ))
    return breaks
