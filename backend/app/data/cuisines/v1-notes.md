# Cuisine graph v1 — editorial notes

## What this release is

The v1 graph is a deliberate starting point for recipe discovery. It has 283 nodes and
318 directed discovery edges. It is broad enough to let a future enrichment model make
useful distinctions already present in the library—for example Cantonese, Sichuan,
Punjabi, Kerala, Peranakan, Nikkei, Cape Malay and Cajun—while still rolling a recipe up
through Chinese, East Asian or Asian; Indian, South Asian or Asian; and so on.

The graph does not say that a broader node owns, creates, or geographically contains a
child. It only supports a retrieval relationship. That distinction matters particularly
for cross-border, diasporic, Indigenous and historically marginalised traditions.

## Model-led research passes

The seed was assembled in five passes:

1. Start with a global frame—Africa, the Americas, Asia, Europe and Oceania—then inspect
   the regional subdivisions that cookbook and food-culture sources commonly distinguish.
2. Add national cuisines where they are useful discovery identities, without forcing a
   country label over a more informative regional or ethnocultural one.
3. Expand countries routinely flattened by global lists: Chinese cuisines include the
   conventional regional families; Indian cuisines include several important regional
   traditions; Indonesian cuisines include Javanese, Sundanese and Minangkabau; Italian,
   Mexican, Brazilian and United States cuisines also receive selected regional nodes.
4. Add traditions that do not fit a one-country tree: Inuit, Māori, Aboriginal Australian,
   Torres Strait Islander, Kurdish, Uyghur, Jewish, Romani and several diaspora and hybrid
   cuisines.
5. Run a negative review: remove dish, ingredient, technique, restaurant-marketing and
   overly generic labels; avoid any edge that would be read as a claim of cultural origin
   or sovereignty.

## Source use

[Wikipedia's List of cuisines](https://en.wikipedia.org/wiki/List_of_cuisines) was the
primary candidate-discovery and gap-audit source because it visibly distinguishes
regional, ethnic, religious, historical and hybrid traditions. It was not imported.
[Wikidata's national-cuisine class](https://www.wikidata.org/wiki/Q1968435) provides the
machine-readable global baseline. [WorldCuisines](https://aclanthology.org/2025.naacl-long.167.pdf)
offers manually reviewed cuisine, country, area and region associations for 2,414 dishes
across 189 countries. UNESCO's intangible-heritage listings are supporting evidence for
specific foodways, rather than a complete taxonomy.

## Deferred work

This is an intentionally reviewable v1, not a claim to enumerate every local foodway.
The coverage manifest records the world regions examined. A v1.1 proposal should add
country-level candidates only where a named cuisine improves discovery, and should be
driven by the pilot's unmapped labels and source-backed cultural review. It must preserve
the current IDs: new releases extend the graph rather than rename or re-parent accepted
nodes without a migration note.
