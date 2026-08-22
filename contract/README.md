# API wire contract

These `*.example.json` files are the **single source of truth for the API wire boundary** —
the exact JSON shape each endpoint emits. They are pinned from *all* consuming sides:

- **Backend** (`backend/tests/test_contract.py`) asserts each Pydantic response model
  serialises (`model_dump(mode="json")`) to exactly the example, and that the live endpoint
  emits the same keys. Rename a field and the round-trip no longer matches → red.
- **Frontend** (`frontend/src/lib/api/contract.test.ts`) asserts the Zod schemas in
  `$lib/api/*` accept the example and reject a drifted copy → red.
- **Android** (`android/app/src/test/kotlin/com/cookmarks/app/ContractTest.kt`) deserialises
  each consumed example into its Kotlin DTO under `gradlew test` → red.

Changing the wire shape is therefore a deliberate edit on every side (model, example, Zod
schema, Kotlin DTO);
an accidental one-sided change fails CI instead of only breaking at runtime in the browser.
