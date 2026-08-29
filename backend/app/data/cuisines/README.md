# Cookmarks cuisine taxonomy seeds

`v1.json` is the reviewed source release for Cookmarks' cuisine discovery graph. It is
data, not a runtime model prompt or an attempt to determine culinary ownership. The
future MY-166 loader will materialise its nodes and directed edges in the database.

## Semantics

An edge is `child -> parent` and means only: a search for the parent may discover a
recipe directly classified with the child. It does not assert that the parent owns,
created, contains, or politically governs the child. A node may have several parents.

Recipes will be linked only to the narrowest supported nodes. Ancestors are calculated
at query time, so a Cantonese recipe can be retrieved through Chinese or East Asian
without also storing those broader labels on the recipe.

## Review model

The initial graph was generated with structured model-led discovery across a global
country-and-territory coverage checklist, then critically reviewed for missing regional,
ethnocultural, Indigenous, diaspora, religious, historical and hybrid traditions.
`Wikipedia's List of cuisines` is a candidate-discovery and coverage-audit source, not
an authority to import. Wikidata's CC0 national-cuisine class, WorldCuisines, UNESCO
and scholarly references provide complementary validation.

Every node and edge inherits the release's `default_provenance` unless it provides a
more specific `provenance` value. New entries need a source or documented editorial
rationale; uncertain candidates belong in a future proposal, not the accepted release.

## File format

The release has three pieces:

- `nodes`: stable lowercase slugs, a display name, one or more kinds, aliases and
  provenance;
- `edges`: two-item `[child, parent]` arrays, with release-level provenance; and
- `coverage`: a review checklist of country or territory coverage and deliberately
  deferred areas.

Aliases are for matching a model or a user query to a canonical ID. They are never
silently shared: a normalised alias may identify one node only. Country names in the
coverage checklist are a review scaffold, not graph parents.

The test at `backend/tests/test_cuisine_seed.py` pins the release format, unique alias
resolution, edge integrity, acyclicity, source references and country coverage.
