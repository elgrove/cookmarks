---
name: work-on-main
description: Interactive co-development directly on the main Cookmarks checkout — the user watches the live app in their browser while the agent edits, managing the honcho dev stack and committing straight to `main` in small verified steps. No worktree, no PR, no ship-it. Use when the user says "work on main", wants to iterate together on the live checkout, or asks for hands-on tweaking while they drive the browser — as opposed to the worktree + PR flow.
---

# work-on-main

Pair-programming mode on the live checkout: the user drives the browser, the agent drives
the editor. Invoking this skill is the user's **explicit, sanctioned exception** to the
worktree rule in CLAUDE.md / AGENTS.md ("never edit the trunk directly") — the boundaries below
are what make the exception safe.

Deliberately **ceremony-free**: no worktree, no PR, no `ship-it`. It exists for iteration
where ceremony would kill the flow — visual tweaks, small fixes, exploratory changes judged
by eye in the browser.

## Session start

- Confirm you're in `/home/aaron/dev/cookmarks` on `main`. If the tree is dirty at the
  start, surface what's there and agree with the user how to fold it in before new work
  (the global stop-and-ask rule still applies to *pre-existing* dirt).
- If `main` is behind `origin/main`, say so and pull before editing.
- Start the stack with `make dev` (honcho: redis, api, web, worker — trunk slot 9) and give
  the user the app URL on the LAN IP: **`http://10.0.0.11:9789`** — never `localhost`.
  Don't use `make dev-auto` here; the trunk slot is the one the user expects.

## The loop

- The user reports what they see; the agent edits; Vite HMR carries most frontend changes
  and `--reload` carries backend ones. **The user's eyes are the primary verifier** — reach
  for `make verify` after harness/unit changes and `make check` before committing, but
  don't grind the full matrix on every tweak.
- Read `DESIGN.md` before touching UI — it's the canonical spec for the look and feel.
- No Playwright, no screenshots, unless the user explicitly asks (their standing rule) —
  the human in the browser replaces the robot.
- **The agent manages the stack** — start, restart, migrate as the work needs. One courtesy
  is non-negotiable: announce *before* bouncing anything the user may be mid-interaction
  with, then do it. Blast radii here:
  - Restarting honcho kills the **Celery worker**, so an in-flight extraction dies with its
    `TaskRun` stuck `RUNNING`. Check for a live run before bouncing.
  - `make migrate` hits the dev DB (`backend/db.sqlite3`) only. Prod has its own volume and
    auto-migrates on container start.

## Prod

There is **no staging**. Prod is the single Docker container on `:8789` (`~/docker/cookmarks`),
and its compose **build context is this checkout** — a deploy ships whatever is checked out
here, committed or not. So: leave the tree on a working state, and deploy only on the
user's word, via the **deploy-prod** skill. Never deploy as a follow-through from a commit.

## Git

- Commit **straight to `main` in small verified steps**: once an increment is confirmed
  working (user says so, or the green signal passes), commit it before starting the next.
  Small commits are the safety net this mode has instead of a PR.
- Normal commit messages in the repo's style; no AI co-author trailers.
- Push only on the user's word.

## Session end

- Summarise the commits made, anything left uncommitted, and whether prod is now behind
  `main` (i.e. a deploy is pending).
- If the session settled decisions or surfaced follow-up work worth keeping, **offer** to
  record it — an offer, not a default.
