# Recipe search

Advanced search adds Field / Operator / Value rules. All or any advanced rules can match;
the resulting condition must also match the main text query and selected keyword chips.
The modal keeps a draft until Apply. Cancel, Escape, and backdrop dismissal discard it.
Cuisine filters match flat keyword names without hierarchy expansion.

The recipe filter chips stay in one frequency-ordered pile. Stable category colours are:
cuisine/region blue, course ochre, dish type rose, key ingredient olive, and method teal.
Uncategorised keywords use neutral ink and surface. A labelled key and accessible names
identify the categories. Selected chips use the forest-green fill with white text.
Light and Midnight colour pairs are defined in `frontend/src/app.css`.

The modal follows the editorial-ledger design: warm paper, Space Grotesk / IBM Plex Mono,
square controls, ink rules, compact spacing, and stacked controls on mobile.

The `filters` query parameter stores a versioned JSON object. It is preserved in recipe
navigation. Semantic search ignores advanced rules; applying them starts normal search.
Keyword category metadata is cached for up to 60 seconds in the API process and up to
60 seconds in the HTTP client. Category changes can therefore take up to two minutes
to appear in a previously cached keyword pool.
