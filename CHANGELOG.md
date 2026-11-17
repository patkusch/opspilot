# Changelog

## November 2026
- A citation file and a contributing guide.
- README test count updated to 33.

## October 2026
- Tests for the API layer: a refused request comes back as a 400, a plan changes nothing until it is approved, and reset puts the data back.
- CI tidied: read-only access, a 15-minute limit, superseded pull request runs cancelled. Weekly Dependabot, a security policy and a CI badge.

## September 2026
- The guardrails are tested from the outside. That found a bug: the age filter was also being used as an amount limit. Fixed.
- A failed verification no longer says "Verified, not asserted".
- The README opens with one real run: asked to write off everything, what the app does and what it refuses.
- MIT licence, and CI on every push.

## July 2026
- First version: a back-office assistant for reconciliation work, built on FastAPI.
