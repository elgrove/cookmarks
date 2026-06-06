# v2 rebuild audit — against v1

A point-in-time audit of the v2 rebuild's feature coverage against Cookmarks v1,
taken just after the **search / similar-recipes** merge.

Roughly **four-fifths through the feature surface**. The browse / search / read /
organise experience is now fully rebuilt and arguably better than v1: lists and
favourites, semantic search, and similar recipes have all landed since the last
audit, alongside two features v1 never had (an in-app EPUB reader and
recipe-in-reader matching). What remains is almost entirely the **extraction
operator surface** — triggering, resuming, monitoring and configuring extraction
from the running app — plus the real background broker that surface depends on.

## Feature-by-feature

| Area | v1 | v2 status | Notes |
|---|---|---|---|
| Domain models | Django models | ✅ Done | All aggregates ported (Book, Recipe, Keyword, RecipeList/Item, ExtractionRun, Config). `RecipeListItem.position` added over v1. |
| v1→v2 data import | — | ✅ Done | 192 books / 13.4k recipes / 13.2k embeddings imported, UUIDs preserved. |
| Books library | `/books/` | ✅ Done + better | Grid, client search, sort, recipe-count circles. |
| Book detail | `/book/<id>/` | ✅ Done | "The Index" layout; random 10-recipe sample; "Browse recipes" action. |
| Book covers | image view | ✅ Done | Config-driven library path, traversal-guarded. |
| Recipe keyword search | `/recipes/` | ✅ Done + better | Substring across name/ingredients/book/keywords; **co-occurrence facets**; seeded random sort; URL-driven state. |
| Recipe detail | `/recipe/<id>/` | ✅ Done | Two-column reading view; prev/next with **book + search** context. |
| Prev/next navigation | HTMX | ✅ Done + faster | Stateless URL-driven; LRU-cached; ~30ms/step. |
| Home / book-of-the-day | `/` | ✅ Done | Stats ledger + daily rotation. |
| Dark mode | basic toggle | ✅ Done + better | "Midnight" theme, OS-aware, no-flash. |
| Extraction pipeline | LangGraph | ✅ **Ported (merged)** | Graph, nodes, AI providers, EPUB parsing, image resolution, rate limiter, reconciliation-by-name. |
| Evals | ad-hoc `_eval/` | ✅ **New, better** | Formal task-first suite, gold books, fuzzy matching, per-field scoring, leaderboard, append-only ledger. |
| AI providers | Gemini/OpenRouter/Stub | ✅ Done | Plus per-role `model_overrides` (new). |
| Lists / collections | `/lists/`, `/list/<id>/` | ✅ **Done (merged)** | Full CRUD over `/api/lists` (create/rename/delete, add/remove recipe); `/lists` index + `/lists/[id]` detail pages; schemas + `contract/list*.example.json` pinned both sides; 4 verify units. |
| Favourites | default-list toggle | ✅ **Done (merged)** | Lazy default **Favourites** list; `POST /api/recipes/{id}/favourite` toggle; ★ button + the once-placeholder "Add to list" picker now wired in `RecipeDetail`. |
| Semantic / vector search | Gemini embeddings | ✅ **Done (merged)** | `VectorStore` + `embeddings.py` ported; `GET /api/recipes/semantic` (with `available` flag); recipes-page `?mode=ai` UI; Gemini-only (Stub gives deterministic offline vectors); contract pinned. |
| Similar recipes | vector cosine | ✅ **Done (merged)** | `GET /api/recipes/{id}/similar` — vector KNN with **shared-keyword fallback** (`basis` flag); lazy footer on recipe detail + `/recipes?similar=<id>` browse page; clean (pre-colon) titles. |
| EPUB reader | — (new) | ✅ **New** | In-app reflowable reader (foliate-js, vendored); `GET /api/books/{id}/epub` (traversal-guarded) + `/books/[id]/read` route; TOC drawer, font-size, theme injection. No reading-position persistence. |
| Recipe-in-reader matching | — (new) | ✅ **New** | Reader recognises which recipe a rendered title names and injects a save-to-favourites pill; `GET /api/books/{id}/recipe-index` + pure-TS title matcher. |
| Extraction trigger (HTTP) | POST `/book/<id>/extract/` | ❌ Missing | Task callable inline only; no endpoint to kick it off from UI. |
| Extraction resume (human-in-loop) | resume form | ❌ Missing | Graph supports interrupt/resume; no HTTP to supply the answer. |
| Extraction reports UI | `/extraction-reports/` | ❌ Missing | `ExtractionRun` model exists; no monitoring view. |
| Tasks/admin dashboard | `/tasks/` | ❌ Missing | — |
| Config / settings UI | `/config/` | ❌ Missing | `Config` model exists; no form to set provider/API key. |
| Calibre sync | `load_books_from_calibre` | ❌ Not ported | v2 imports from v1's DB, not Calibre's `metadata.db` directly. No live re-sync path. |
| Keyword dedup | AI-assisted merge | ❌ Not ported | Prompt exists in v2; never invoked. |
| Recipe image serving | EPUB-zip stream | ❌ Missing | No standalone recipe-image endpoint; `has_image` reported only. (Images do render inline inside the EPUB reader.) |
| Background broker | django-q2 worker | ⚠️ Skeleton | Celery on `memory://` — no real broker (Redis) wired. |
| Auth | none (single-user) | ✅ Matches (intentional) | — |

## The remaining gap: extraction's operator surface

The extraction **pipeline and eval harness** are merged — the proven logic is
faithfully ported and testable. But the **operational surface around it is still
not there**: no HTTP trigger, no resume endpoint, no reports/monitoring view, no
config UI, and the Celery broker is still `memory://`. So you can run extraction
from a test/eval, but a user can't yet kick one off, answer the human-in-the-loop
image question, or watch it progress from the running app.

This is now the dominant remaining milestone. A coherent slice covers:

- **Trigger**: `POST` to start `extract_recipes_from_book` for a book, returning a run id.
- **Resume**: an endpoint to supply the human-in-the-loop answer to the graph's
  interrupt (image-matching question), resuming the checkpoint.
- **Reports / monitoring**: surface `ExtractionRun` (method, chapter progress,
  image flags, cost/tokens, status) — a runs list + per-run detail.
- **Config / settings UI**: a form over the `Config` singleton (provider, write-only
  API key, rate limit) so a user can configure extraction without touching the DB.
- **Real broker**: replace `memory://` with Redis so runs execute in the background
  and survive restarts — the trigger/resume/monitoring surface assumes this.
- **Harness/contract**: verify units + pinned contract examples for each new surface,
  following the established pattern.

Smaller, independent leftovers: standalone **recipe image serving**, **Calibre
live re-sync** (v2 currently imports from v1's DB, not `metadata.db`), and the
AI-assisted **keyword dedup** (prompt exists, never invoked).

## What v2 adds beyond v1

The verify harness (architectural, **13 units**), both-sides wire-contract pinning,
co-occurrence keyword facets, seeded-deterministic random ordering, per-role model
overrides, the formal eval suite, the polished editorial design system + dark theme,
and two features v1 never had — an **in-app EPUB reader** and **recipe-in-reader
matching** (save-to-favourites straight from the page you're reading).
