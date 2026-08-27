---
name: plan-ticket
description: Interactively scope and design a Linear ticket, then write the agreed implementation plan into the ticket description so any agent can implement it cold. Use whenever the user wants to plan, scope, spec, or design a Linear ticket, or discuss approach before building — "plan MY-65", "let's spec the search ticket", "scope this out before we build it" — including when they name a ticket ID and the intent is design discussion rather than writing code.
---

# plan-ticket

Turn a rough Linear ticket into an implementation plan, agreed with the user, recorded on
the ticket. The board is the shared memory of a multi-agent workflow: the deliverable is
**not this conversation, it's the updated ticket**. The bar for done: an agent with no
access to this conversation could implement the ticket from its description alone.

This is the interactive half of the plan/implement split — design risk is the user's to
accept, so work the decisions through *with* them. (Implementation runs unattended via the
`implement-ticket` skill; this is the last point where questions are cheap.)

## Flow

### 1. Load the full context

- Fetch the ticket with comments using the available Linear MCP or connected Linear app
  tools. If no Linear connection is available, report that blocker before changing files.
- Read related/blocking issues and the project description; check project documents for
  cross-cutting rules the plan must honour.
- Read `CLAUDE.md` for conventions, `DESIGN.md` for anything touching UI, and then **read
  the actual code** the ticket touches (read-only — no worktree needed). Plans that name
  real files, real functions, and real schema state are executable; plans written from
  memory are fiction.
- If the user gave a description instead of a ticket ID, create the ticket first
  (team/project resolved from context) and plan onto it.

### 2. Design it together

Ask me questions to nail down the functionality, design and architecture. Iterate until I
call the plan agreed.

### 3. Write the plan into the ticket description

Replace the description with the agreed plan, **preserving the original "why"** (rework it
into the Context section — never lose the motivation). Structure:

```markdown
# <Title restated>

## Context
Why this exists, what it builds on, links to related tickets.

## Decisions
Dated bullets for anything settled during planning ("Decision 2026-07-11: …").

## Plan
### Step 1 — <name>
What to change: real file paths, Alembic migrations, model/wire-contract changes, new packages.
How to verify this step (`make check` / `make test` / `make verify`, specific tests, fixtures).
### Step 2 — …

## Dependency order
Which steps gate which; what can parallelise.

## Out of scope
What this ticket deliberately does not do (and where that work lives instead).

## Open questions
Only if genuinely unresolved — each one blocks an identified step, not the whole ticket.
```

Cookmarks specifics a plan must name explicitly when in play:

- **UI units**: which component gets a `data-verify-*` contract, its fixtures (including
  the required probe) and invariants — a UI step without its verify unit isn't planned.
- **Wire contract**: any Pydantic/Zod change needs its `contract/*.example.json` updated on
  both sides, or CI fails.
- **Schema**: name the migration and whether it needs a backfill; `recipe_embeddings` is
  outside Alembic.
- **Background work**: new task types go through the `app/tasks/runs.py` seam and surface
  in `TaskRunRead`.

Plan rules:

- The plan is a **snapshot, not a narrative** — never "scope expanded during planning" or
  "after discussion we chose X"; just state the current plan (decisions carry the dates).
- Include code only when it's load-bearing (a schema, a wire contract, a tricky SQL shape)
  — not sketches of ordinary code the implementer would write anyway.
- Keep comments for history: if the description previously carried significant content
  that the plan supersedes, note that in a comment rather than silently deleting.

### 4. Status and handoff

- When the user declares the plan agreed: move the ticket **Backlog → Todo** (it is now
  pick-up-able) and set priority if the user indicated one.
- Offer — don't assume — to kick off `implement-ticket` on it.

## Rules

- British spelling throughout ticket content.
- Never fabricate file paths or API shapes — every concrete reference in the plan must
  have been verified against the codebase during step 1.
- Multiple tickets in one session are fine, but plan them one at a time to completion.
