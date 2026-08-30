# Cookmarks cuisine taxonomy seeds

`v1.json` is the versioned source seed for Cookmarks' cuisine discovery graph. It is
data, not a runtime model prompt, a claim of comprehensive coverage, or an attempt to determine culinary ownership. The
future MY-166 loader will materialise its nodes and directed edges in the database.

## Semantics

An edge is `child -> parent` and means only: a search for the parent may discover a
recipe directly classified with the child. It does not assert that the parent owns,
created, contains, or politically governs the child. A node may have several parents.

Recipes will be linked only to the narrowest supported nodes. Ancestors are calculated
at query time, so a Cantonese recipe can be retrieved through Chinese or East Asian
without also storing those broader labels on the recipe.

## Review model

The initial graph was generated with structured model-led discovery across broad world
regions, then critically reviewed for named regional, ethnocultural, Indigenous,
historical and hybrid foodways.
`Wikipedia's List of cuisines` is a candidate-discovery and coverage-audit source, not
an authority to import. Wikidata's CC0 national-cuisine class, WorldCuisines, UNESCO
and scholarly references provide complementary validation.

Every node and edge inherits the release's `default_provenance` unless it provides a
more specific `provenance` value. New entries need a source or documented editorial
rationale; uncertain candidates belong in a future proposal, not the accepted release.

## File format

The release has three pieces:

- `nodes`: stable lowercase slugs, a display name, one or more kinds and aliases;
- `edges`: two-item `[child, parent]` arrays, with release-level provenance; and
- `coverage`: a regional review manifest and deliberately deferred areas.

Aliases are for matching a model or a user query to a canonical ID. They are never
silently shared: a normalised alias may identify one node only. Geography in the
coverage manifest is a review scaffold, not graph parentage.

`backend/tests/test_cuisine_seed.py` validates node and alias uniqueness, edge
integrity, acyclicity and release-level provenance references.
