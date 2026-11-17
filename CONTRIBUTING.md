# Adding to OpsPilot

Small, focused changes are welcome. Open an issue first for anything large.

## Before you push

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m compileall -q app
python -m pytest -q
```

Then start the app with `uvicorn app.main:app --port 8765` and check that the page and `/api/state` both load. CI does the same.

## What every change comes with

- A test that fails without the change and passes with it.
- The guardrails stay outside the assistant's reach. A change must never let it write off money above its limit, or skip the second check that adds the sums up again.
- The sample ledgers are made up. Never add a real organisation's figures.
- Plain English in anything a person reads, with the plain meaning next to every number.
