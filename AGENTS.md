# Working in opspilot

Agentic back-office ops copilot for financial services — chat an intent, the agent plans and acts on the reconciliation-breaks queue, a human approves, and every outcome is proven against the ledger. Guardrails enforced in code.

## Run the tests

The checks run on Python 3.12.

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

Every test should pass before you start and after you finish.

## Where things are

- `app/`: the application code
- `static/`: files served to the browser
- `tests/`: the tests
- `docs/`: written documentation

## Before you commit

- Make sure the tests pass.
- Put changes people will notice in `CHANGELOG.md`.
- Do not put real passwords, keys or private data in test files or examples. Use made-up ones.
