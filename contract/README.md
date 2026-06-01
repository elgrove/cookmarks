# API wire contract

These `*.example.json` files are the **single source of truth for the backend ↔ frontend
boundary** — the exact JSON shape each endpoint emits. They are pinned from *both* sides:

- **Backend** (`backend/tests/test_contract.py`) asserts each Pydantic response model
  serialises (`model_dump(mode="json")`) to exactly the example, and that the live endpoint
  emits the same keys. Rename a field and the round-trip no longer matches → red.
- **Frontend** (`frontend/src/lib/api/contract.test.ts`) asserts the Zod schemas in
  `$lib/api/*` accept the example and reject a drifted copy → red.

Changing the wire shape is therefore a deliberate three-step edit (model, example, Zod schema);
an accidental one-sided change fails CI instead of only breaking at runtime in the browser.
