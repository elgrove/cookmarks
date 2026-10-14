# Recipe search

Advanced search adds Field / Operator / Value rules. All or any advanced rules can match;
the resulting condition must also match the main text query and selected keyword chips.
The modal keeps a draft until Apply. Cancel, Escape, and backdrop dismissal discard it.
Cuisine filters match flat keyword names without hierarchy expansion.

The recipe filter chips stay in one frequency-ordered pile. Cuisine/region uses pastel
blue, course uses pastel green, method uses lavender, and key ingredient uses peach.
Dish type and uncategorised keywords use ten decorative pastels: peach,
sand, rose, lavender, mauve, butter, coral, periwinkle, seafoam, and sage. The palette has
12 colours in total. A keyword's name determines its decorative pastel so it stays stable
across result ordering and page reloads. Decorative colours do not indicate categories.
All unselected chips use the same quiet outline. Cuisine and course use darker category
text; other keywords use grey text. Accessible names identify every category. Selected
chips use the forest-green fill with white text. Light and Midnight colour pairs are
defined in `frontend/src/app.css`.

The modal follows the editorial-ledger design: warm paper, Space Grotesk / IBM Plex Mono,
square controls, ink rules, compact spacing, and stacked controls on mobile.

The `filters` query parameter stores a versioned JSON object. It is preserved in recipe
navigation. Semantic search ignores advanced rules; applying them starts normal search.
Keyword category metadata is cached for up to 60 seconds in the API process and up to
60 seconds in the HTTP client. Category changes can therefore take up to two minutes
to appear in a previously cached keyword pool.

Advanced search is in the upper search row. Book and author selection is available in
the modal. Older search links still apply their book and author filters and show removable
summaries. The main page retains its sort control.
