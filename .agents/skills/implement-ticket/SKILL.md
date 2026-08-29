---
name: implement-ticket
description: Autonomously implement a Linear ticket end-to-end — mark it In Progress, build in a Cookmarks sub-worktree, verify, ship a PR via the ship-it skill, link the PR back and set the ticket In Review. Use whenever the user asks to implement, build, do, or pick up a Linear ticket — "implement MY-62", "build MY-65", "pick up the search tickets" — including when they pass several ticket IDs at once.
---

# implement-ticket

Take a Linear ticket from Todo to an open PR, unattended. The user may be gone the whole
run: **never block on a question** — the ticket is the communication channel. The end state
is a green PR awaiting the user's review, with the ticket telling the full story.

The ship-it skill owns the delivery tail (pre-flight checks, subagent review, PR, CI-green
loop, frontend screenshots); this skill owns everything before and after it.

## Phase 0 — The ticket

- Fetch the ticket **with comments** using the available Linear MCP or connected Linear app
  tools. Comments often carry decisions and constraints newer than the description — read
  them all. If no Linear connection is available, report that blocker before changing files.
- A plan in the description (from `plan-ticket`) is the steer — follow it. No plan is not
  a blocker: use judgment, guided by `CLAUDE.md` and the board's related tickets.
- Multiple tickets: implement **sequentially**, one branch + one PR each, ordered by
  dependency (blocked-by relations, or logical order). Never interleave.
- Mark the ticket **In Progress** before touching code.

## Phase 1 — Environment

- Create a sub-worktree using the repository's agent rules. Fetch `origin` first, identify
  the default branch, and use the required worktree location:

  ```bash
  cd ~/dev/cookmarks
  git fetch origin
  mkdir -p ~/home/.worktrees/cookmarks
  git worktree add -b <branch> ~/home/.worktrees/cookmarks/<branch> origin/<default>
  ```

- Work only inside the sub-worktree. Keep the repository's default checkout unchanged.
  Use the branch style shown by `git log` (for example, `feat/<slug>` or `fix/<slug>`),
  not Linear's suggested name.
- `make install` in the worktree if deps changed; `make migrate` for a new migration.
- If the work needs a running app, use `make dev-auto` (slots 2–7) — **never** the trunk
  slot 9 or prod slot 8, and never point the worktree at the trunk's services or ports.
- Read `AGENTS.md` and, when present, `CLAUDE.md`. For UI work, read `DESIGN.md` when
  present; these files are the canonical project specifications.

## Phase 2 — Implement

- Small verified commits. Green signals: `make check` (ruff + ty + svelte-check),
  `make test`, and `make verify` (the fixture matrix) after any UI or harness change.
- New or changed UI unit → its `*.verify.ts` with fixtures, ≥1 probe, and invariants over
  the `data-verify-*` contract. Changed wire shape → update `contract/*.example.json` so
  both Pydantic and Zod sides stay pinned.
- Fixture the way the repo fixtures (capture a real input, assert the output).
- **Deviations — judgment with a written trail.** When reality contradicts the plan:
  - If the plan's *intent* survives via a different mechanism (an endpoint moved, a
    helper already exists, a column is named differently) → adapt, and record the
    deviation + rationale as a **ticket comment before carrying on**, so the trail exists
    even if the run dies later.
  - If the intent itself is broken (the data source is gone, the approach can't work) →
    **stop**: push the branch as-is, comment the situation and the options on the ticket,
    leave it In Progress, end the run. A wrong guess costs a bad merge; a stopped run
    costs a re-plan. Stop is cheaper.
- Never widen scope beyond the ticket. Adjacent problems discovered en route become
  ticket comments (or, if clearly separate work, a suggestion in the close-out comment to
  ticket them) — not extra commits.

## Phase 3 — Ship

- Invoke the **ship-it** skill from the worktree: it handles dirty-tree commits,
  pre-flight checks, the comprehensive subagent review, PR creation, and watching CI to
  green. Let it run its full flow.
- PR title/body must reference the ticket ID (e.g. "MY-62") so the PR and board
  cross-navigate.
- If the diff touches frontend files, confirm the PR body actually carries the
  screenshots ship-it takes — a frontend PR without screenshots is not done.

## Phase 4 — Close the loop on the board

- Attach the PR URL to the ticket (links/attachment).
- Write the close-out comment: what was built, how it was verified (name the signals
  run), any deviations from the plan, and **operational steps documented — never run**:
  migrations against the prod volume, data loads, a deploy. Give the exact commands.
- Set the ticket to **In Review** (fall back to leaving it In Progress with a note if the
  workspace has no such state).
- **Never**: merge the PR, merge into the trunk, remove the worktree, deploy (the
  `deploy-prod` skill is the user's to invoke), or mark the ticket Done. Prod builds from
  whatever is checked out in `~/dev/cookmarks`, so a stray trunk change ships on the next
  deploy. Done happens when the user merges (always via squash merge).


## Failure honesty

If the run ends anywhere short of a green PR, the ticket must say so — state reached,
what's pushed, what's broken, what the options are. A silent dead branch is the one
unacceptable outcome.
