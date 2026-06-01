# DESIGN.md — Cookmarks v2 UI design language

The single source of truth for **how the Cookmarks v2 interface looks and feels**. Build directly
from this document. `CLAUDE.md` owns the *architecture* (FastAPI backend + SvelteKit SPA + the
verification harness); this file owns the *visual & interaction language*.

---

## 1. Product

Cookmarks is a **single-user, self-hosted** app for browsing and searching the recipes extracted from
a personal Calibre cookbook library (~192 books, ~13,000 recipes). It is a private reference tool, not
a social or publishing product. The whole experience should feel like a **warm, meticulously kept
reference library**: calm, precise, text-led, and quietly beautiful. No marketing gloss, no dashboard
clutter, no decorative noise.

---

## 2. Design language

A **warm editorial archive**: the precision of a well-kept index — hairline rules,
abundant whitespace, typography doing the heavy lifting — softened by warmth and human craft. The palette and type take their cue from **Anthropic's brand identity, designed by
Geist** ([geist.co/work/anthropic](https://geist.co/work/anthropic)): warm off-white grounds, a single
clay accent, and a refined grotesque-with-serif pairing — "technically refined and charmingly quirky."

### Principles

1. **Text-first.** Most recipes have **no image**. Every layout must be excellent and complete with
   pure type; imagery is a bonus, never load-bearing. Designing the *absence* of an image is a
   first-class concern — see §7.
2. **Precision over decoration.** Delineate with **hairline rules and whitespace**, not heavy cards or
   drop-shadows. Everything aligns to a modular grid.
3. **Warm, not cool.** Ivory paper, near-black ink, one clay accent. Inviting, never clinical.
4. **Typography is the interface.** A strict three-family hierarchy (grotesque / serif / mono) carries
   almost the entire identity. Keep the rhythm and hierarchy crisp.
5. **Restraint with the accent.** Clay marks only moments of emphasis (active nav, step counters,
   key actions, hover). If everything is clay, nothing is.
6. **Archival structure.** `label · value` metadata tables, hairline rules, and small letterspaced
   mono section labels. This is the recurring structural motif.

### Stay away from

Generic AI aesthetics — Inter/Roboto/Arial/system fonts, purple gradients, heavy shadowed cards,
predictable centred templates. No cool greys. No purely decorative glyphs or "logo motif" gimmicks;
the wordmark is simply **Cookmarks** set in the grotesque.

---

## 3. Design tokens

### 3.1 Colour (CSS custom properties — these values are authoritative)

| Variable | Hex | Role |
|---|---|---|
| `--bg` | `#faf9f5` | Page ground (warm ivory) |
| `--bg-warm` | `#f3efe5` | Subtle panels / bands (e.g. stat ledger, footer, typographic plate) |
| `--ink` | `#141413` | Primary text & dark blocks. **All body / reading copy.** |
| `--muted` | `#86847b` | Secondary text, labels |
| `--faint` | `#b0aea5` | De-emphasised text, captions, disabled, separators |
| `--line` | `#e8e6dc` | Hairline rules / borders (default) |
| `--line-strong` | `#d8d4c6` | Stronger hairline (section dividers) |
| `--clay` | `#d97757` | **The accent.** Active nav, step counters, hover, key actions, emphasis. Used sparingly. |
| `--clay-deep` | `#c2613f` | Clay for text/links needing more contrast; hover-darken |

**Category chip tints** (rotating, for keyword/category chips only — never as body text colour):

| Variable | Value | |
|---|---|---|
| `--chip-clay` / `--chip-clay-c` | `rgba(217,119,87,.11)` / `#d97757` | bg tint / label colour |
| `--chip-blue` / `--chip-blue-c` | `rgba(106,155,204,.11)` / `#4c7fa8` | |
| `--chip-green` / `--chip-green-c` | `rgba(120,140,93,.11)` / `#5c7245` | |

Rotate chip colours by keyword for gentle variety; keep backgrounds at ~11% tint with the solid colour
for the label only. (The clay/blue/green accents derive from Anthropic's accent set; chip label colours
are darkened for legible contrast on the tint.)

> **Theme:** light only. A future warm-dark mode would invert to an ink ground / ivory text with clay
> preserved — out of scope until specified.

### 3.2 Typography

Three families, strict roles — a refined grotesque for structure, a warm serif for reading, and a mono
for the index/metadata layer. (In the spirit of Anthropic's Styrene + Tiempos pairing; see §2.)

| Family | Variable | Role | Weights |
|---|---|---|---|
| **Schibsted Grotesk** | `--f-grotesk` | Headings, nav, buttons, labels, UI chrome. Often letterspaced uppercase at small sizes. | 400/500/600/700 + italic 400/500 |
| **Source Serif 4** | `--f-serif` | **Body & reading**: descriptions, ingredients, method steps, and large display titles (often italic). | 300/400/500/600 + italics; optical size 8–60 |
| **IBM Plex Mono** | `--f-mono` | Metadata, tabular data, section labels. Letterspaced uppercase for labels. | 300/400 + italics |

```css
--f-grotesk: 'Schibsted Grotesk', 'Helvetica Neue', sans-serif;
--f-serif:   'Source Serif 4', Georgia, serif;
--f-mono:    'IBM Plex Mono', 'Courier New', monospace;
```

- **Hierarchy rule:** headings = grotesque, reading copy = serif, data/labels = mono. Never mix roles.
- **Display titles** (recipe, book, page titles) are large **Source Serif 4**, frequently *italic*.
- **Self-host the fonts** via `@fontsource` packages (`@fontsource-variable/source-serif-4`,
  `@fontsource/schibsted-grotesk`, `@fontsource/ibm-plex-mono`) — the app is single-origin and
  self-hosted and must make no external font requests.

Helper classes:
```css
.label { font-family: var(--f-mono); font-size:.65rem; letter-spacing:.14em;
         text-transform:uppercase; color: var(--muted); }   /* section supra-labels */
.mono  { font-family: var(--f-mono); font-size:.72rem; letter-spacing:.08em; }
```

### 3.3 Layout & shape

| Variable | Value | Role |
|---|---|---|
| `--max-w` | `1200px` | Max content width (centre with auto margins) |
| `--col-gap` | `3rem` | Gap between primary columns |
| `--page-h` | `5rem` | Page horizontal padding (reduce on mobile) |
| `--border` | `1px solid var(--line)` | Default hairline |
| `--border-strong` | `1px solid var(--line-strong)` | Section divider |
| `--ease-out` | `cubic-bezier(.16,1,.3,1)` | Standard easing |

- **Radius:** minimal — small radii (≤4px) or square edges. Cover images and panels use a thin hairline
  border, not rounding.
- **Elevation:** essentially none. **No drop-shadow cards.** Separate with hairlines + whitespace.
- **Negative space is part of the identity** — let pages breathe; don't crowd.

### 3.4 Motion

- **One orchestrated on-load reveal:** a staggered `fadeUp` via CSS `animation-delay`
  (`animation-fill-mode: both`, completing within ~1.2s). Hover: a subtle underline / colour shift.
- **Never gate reveals on scroll.** Content must be fully visible without scrolling and even if
  JavaScript never runs — entrance animations may *enhance* but must never determine visibility.
- Honour `@media (prefers-reduced-motion: reduce)` — disable transforms, force `opacity:1`.

---

## 4. Structural patterns

The recurring building blocks that give the UI its archival character:

- **Hairline metadata tables** — `LABEL · value` rows (mono label in `--muted`, serif or mono value),
  separated by hairlines. Used for book and recipe metadata.
- **Mono section labels** — small letterspaced uppercase labels above sections (`INGREDIENTS`,
  `FROM THE BOOK`, `METHOD`).
- **Text-first list rows** — list entries are typographic rows (name + right-aligned source + keyword
  chips), **with no thumbnails**, so the presence or absence of an image never affects layout.
- **Breadcrumbs** — plain, e.g. `Books › Author › Title`, in mono at small size.

---

## 5. Components

Build each as a **presentational component** (props in; no data fetching; no router/`$app/*` imports)
so it can mount in isolation in the verification harness (§9). Routes do the fetching and pass props in.

- **App shell / top nav** — **Cookmarks** wordmark (grotesque); nav: Home · Books · Recipes (search) ·
  Lists. Active item = **clay underline**. Ivory background, hairline bottom border. Collapses to a
  drawer on mobile.
- **Book card** — cover as a small bordered "plate" (hairline border, `2:3`, `object-fit:cover`); a
  **recipe-count circle** in the cover's top-right corner (clay fill, ivory numeral) showing how many
  recipes were extracted — **unextracted books show no circle**; title (serif); author (`--muted`).
  Missing covers → §7.
- **Book grid + controls** — responsive grid of book cards; a controls bar with **search**, **sort**
  (Recently added / Title A–Z / Author / Most recipes) and **author filter**; a total count. With a
  library of this size, filtering and sorting are **client-side**.
- **Recipe row** — a text-first list row: recipe name (serif) · book & author (right, `--muted`) ·
  keyword chips; **no leading number, no thumbnail**. The unit of book-detail lists, search results,
  and featured lists.
- **Recipe masthead** — breadcrumb · a mono metadata line (book · author) · **large serif
  (often italic) title** · favourite (★) toggle · yields · keyword chips. Shared identically by the
  with-image and no-image recipe layouts.
- **Recipe image vs no-image** — the key component decision; see §7.
- **Ingredients** — serif list; supports sub-group subheads (e.g. *For the sauce*, *To finish*);
  optional check-off interaction.
- **Method** — numbered steps with **clay mono step numbers** in a fixed gutter and **serif step text**;
  optional group headers (e.g. *Day 1 / Day 2*). Render every step.
- **Metadata table** — `LABEL · value` hairline rows (yield, course, time, keywords, image, extraction).
- **Keyword chips** — small rounded-rect, rotating tint backgrounds (§3.1); link to filtered search.
- **Provenance ("From the book")** — small cover plate + book title + author, links to the book.
- **Add-to-list control** — choose an existing list (Favourites, Weeknight dinners, To try…) or create
  a new one.
- **Buttons** — grotesque, weight 600; primary = ink or clay fill; secondary = hairline outline.
- **Prev/next, pagination, similar-recipes** — text-first, as list rows.
- **Empty / loading / error states** — designed in the same language (calm hairline skeletons for
  loading; a plain serif message such as "No recipes extracted yet" for empty). Never an afterthought.

---

## 6. Screens

| Screen | Purpose & key content |
|---|---|
| **Home** | A quiet landing, distinct from Books. Hero; a stats ledger (books · recipes · keywords); a "Book of the day" feature; quick-access links; a short index of featured recipes. |
| **Books library** | The collection: book-card grid with search + sort + author filter and a total count. |
| **Book detail** | Cover plate + title + author + a metadata table (publisher, ISBN, pages, recipe count, added, last extraction run); a **recipe index** of the book's recipes; actions (Read book / Re-extract / Add to list). |
| **Recipe detail** | The reading view (see masthead, §5): with an image it appears as a bordered figure with a mono caption; **without an image, the no-image treatment of §7 applies**. Ingredients; full numbered method; any cooking-guide table; provenance; add-to-list; prev/next; similar recipes. |
| **Search / browse** | A prominent search field; a **semantic / natural-language search** affordance ("Describe what you fancy…"); filters (keywords, book, author, favourites); sort; a result count; results as text-first list rows; pagination. **The list is empty until a query is entered** — the resting state is a calm prompt to search, not a dump of every recipe. |
| **Lists** | Collections, including a default **Favourites**; a grid of lists; create / rename / delete; opening a list shows its recipes as a filtered index. |

Features the UI must accommodate: **Favourites** (a default list, toggled by the ★ on a recipe),
**semantic/vector search** alongside keyword search, **keyword filtering** (clickable chips), and
field-level filters (name, ingredients, keywords, author, book).

---

## 7. Image policy — design the *absence* (most important rule)

Most recipes have **no image**, and some book covers will be unavailable. Missing imagery must read as
a deliberate design state — **never** as a broken or apologetic gap.

- **Recipe with image** — a **bordered figure** (hairline border) with a mono caption naming the source.
- **Recipe without image** — a **typographic plate** in the same position: a `--bg-warm` panel with a
  hairline border holding the recipe's **large light-italic serif drop-initial** (its first letter)
  beside its **opening line** set in italic serif. No empty box, no "no image available" text. The
  masthead is otherwise identical to the with-image layout.
- **Metadata honesty** — the metadata table states `IMAGE · None in source` rather than hiding it.
- **Lists & grids are text-first** — recipe rows carry no thumbnails, so image presence never affects
  layout. Only **book covers** use imagery; a missing cover falls back to a hairline plate bearing the
  title in serif (the same plate language).

A text-first, type-led design is the whole point: the interface must be genuinely excellent without a
single photograph.

---

## 8. Responsiveness & accessibility

- **Breakpoints:** intentional at **390px** (mobile) and **1280px** (desktop). Two-column recipe/book
  layouts stack; metadata tables reflow to stacked `label / value`; the book grid drops to 2 columns
  then 1; nav collapses to a drawer.
- **No horizontal scroll** on mobile — clip any decorative/fixed background layers so they don't inflate
  scroll width.
- **Contrast:** clay `#d97757` on ivory is ~2.6:1 — **never use clay for body / reading text.** Use
  `--ink` for all reading copy; clay is for accents, large display, borders, icons, and decorative
  numbers. For clay-coloured *links/labels* prefer `--clay-deep` and/or an underline so colour is not
  the only signal.
- **Semantics:** real headings, lists, `<table>`/`<dl>` for metadata, labelled controls, visible focus
  states (clay outline), `alt` on cover/recipe images (decorative typographic plates are `aria-hidden`).
  The favourite toggle is a real `button[aria-pressed]`.

---

## 9. Implementation notes

Tie the design to the v2 architecture (see `CLAUDE.md`):

- **Every UI unit ships a verification contract.** Emit `data-verify-*` attributes on a self-identifying
  root (e.g. `data-verify-unit="books-library"` plus state attributes the invariants read, like
  `data-verify-count`, `data-verify-empty`), and add a co-located `*.verify.ts` default-exporting a
  `VerifiableUnit` (fixtures including ≥1 `probe`, invariants, optional Zod `propsSchema`).
- **Components are presentational** (props in) so they mount at `/verify/:unit/:fixture` without
  `$app/*` imports; **routes** do data fetching and pass props in. Harness tests stay free of
  SvelteKit imports.
- **Tokens module:** put the §3 CSS variables and helper classes in a global stylesheet (e.g.
  `src/app.css`) and self-host fonts via `@fontsource`.
- **Suggested first slice:** **`/books`** — a `GET /api/books` endpoint (id, title, author,
  recipe_count, has_cover, pubdate), a `BooksLibrary` presentational + verifiable component, and a
  `/books` route. Serve covers via `GET /api/books/{id}/cover` (stream `<calibre-library>/<book>/cover.jpg`;
  the library path is configurable). Books with no cover render the hairline title-plate (§7).

---

## 10. Reference

- Anthropic brand identity by Geist — the inspiration for the warmth, palette, and type pairing:
  **[geist.co/work/anthropic](https://geist.co/work/anthropic)**.
