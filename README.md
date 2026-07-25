<div align="center">

# OpsPilot

**Chat an intent. The agent inspects the breaks queue, plans, acts — and *proves* the outcome.**

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![No keys](https://img.shields.io/badge/runs-with%20zero%20API%20keys-2b7a3b)
![License](https://img.shields.io/badge/license-MIT-blue)

The last metre of agentic back-office operations for financial services.

</div>

---

## The problem

A bank's reconciliation team drowns in **breaks** — mismatched entries between ledgers and
counterparties. Most are trivial (a duplicate, a timing difference) and could be cleared in
seconds; a few are large or ambiguous and genuinely need a human. Today an analyst grinds
through the queue by hand, and the risky ones get the same casual attention as the trivial ones.

An agent could clear the volume in seconds. But you cannot let software silently write off
money or match entries it only *thinks* offset — and you cannot take its word that it worked.

## The answer: the agent does the volume, a human keeps control — and the outcome is proven

You type an intent in plain English. The agent:

1. **Parses** the intent into a structured, explainable reading (action + filters).
2. **Plans** a disposition for every matching break — and runs each past hard guardrails.
3. Waits for a **named human to approve the run** (the agent can never authorise its own).
4. **Executes** the eligible actions, then **verifies the outcome against the ledger** and
   reports the arithmetic that proves it. Anything it can't do safely is **escalated to a human**.

> *"Cleared 34 breaks, £128k reconciled, ledger balanced ✓ — 3 over-threshold items escalated
> to a human. **Verified, not asserted.**"*

## Guardrails — enforced in code, not in a prompt

| Guardrail | Rule | Where |
|---|---|---|
| **Dual control** | Nothing at/over **£10,000** is ever automatic — human only | [`engine.py`](app/engine.py) `_decide` |
| **Write-off limit** | The agent may write off at most **£250** per item | [`engine.py`](app/engine.py) `_decide` |
| **Freshness** | Only breaks **≥ 30 days** old are write-off candidates | [`engine.py`](app/engine.py) `_decide` |
| **Batch cap** | At most **£5,000** written off in a single run; the rest escalate | [`engine.py`](app/engine.py) `build_plan` |
| **Auto-match needs proof** | Only breaks with a real **offsetting entry** may be matched | [`engine.py`](app/engine.py) `_decide` |
| **No self-authorisation** | A run needs a **named human**; operator `agent` is rejected | [`store.py`](app/store.py) `run` |
| **Outcome is proven** | Conservation of value + "cleared breaks actually gone" checked post-run | [`engine.py`](app/engine.py) `execute_and_verify` |

Ask the agent to *"write off everything"* and the £40k breaks don't get written off — they get
**escalated**, because the guardrail has the final say, not the request.

## The verification model — prove, don't trust

After executing, OpsPilot runs checks that must pass or the run is marked failed:

- **Conservation of value** — every pound that left the open queue is either *reconciled* or
  *escalated*; nothing vanishes (`before − after == reconciled + escalated`).
- **Cleared breaks actually gone** — the cleared items are confirmed no longer open.
- **No over-limit item auto-actioned** — every automatic action was under the dual-control line.
- **Write-off cap respected** — the agent stayed within its batch limit.

## Stack

- **Python + FastAPI** backend, Pydantic domain models, in-memory store (resets on restart)
- Deterministic agent core in [`app/`](app) — **no LLM key required**; a rules-based intent
  parser stands in for the model so the demo runs offline. The `parse_intent` seam is where a
  Claude call (`claude-opus-4-8`) would slot in for free-form intent.
- Single-file **ops-console** frontend ([`static/index.html`](static/index.html)), no build step

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

Try: `clear the low-value GBP breaks under 500`, then `write off everything` and watch the
large items get escalated instead.

## Design lineage

OpsPilot "steals like an artist" from three hackathon-winning projects:

- **SipQuest** — *natural-language intent → a verified real-world action*, with hard safety
  constraints on what the agent may do unattended.
- **RuleLift** — *prove, don't trust*: the outcome is checked against the ledger; the agent
  never reports success it can't demonstrate.
- **Remedia** — *control beats autonomy*: guardrails live in code, human approves the run,
  every action is audited.

---

<div align="center">
<sub>Synthetic breaks queue, illustrative figures · MIT · the agent does the volume, a human keeps control.</sub>
</div>
