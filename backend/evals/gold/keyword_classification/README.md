# Keyword classification quality

The default sample, `top1000-sample.json`, is a uniform random sample of 100
keywords from the top 1,000 by distinct recipe use in production on 2026-10-11.
The population cutoff is 22 recipes. Selection uses seed 20261011; ties in rank
are sorted by keyword name. Stored recipe counts and ranks make the snapshot
reviewable without querying production again.

The sample expects curry, cake, kofta, roll, soup, and salad to be `dish_type`;
homemade has no category, and Roman is cuisine/region. `dish_type` describes what
a recipe makes; `course` describes its meal or serving role. Named sauces can
be dish types, while familiar ingredient names remain ingredients. The sample
allows either ingredient or dish type for mayonnaise, custard, and béchamel.

`top100.json` is a secondary sample containing the 100 keywords used by the most
recipes in the production snapshot from 2026-10-11. Each has at least 348 recipe
uses. Together they account for 58.5% of recipe-keyword links and appear on 28,903
of 28,908 recipes. Counts are distinct recipes per keyword.

Expected labels incorporate the user's corrections. The remaining labels are
agent-authored and need review. Some broad food terms have multiple acceptable
labels in `accepted`. Review those expectations before using the sample as a
production release gate. The report includes accuracy weighted by recipe use;
that measures keyword links, not unique affected recipes, because recipes have
several keywords.

`keywords.json` is a secondary 65-keyword boundary sample. The user's accepted
labels for `brine` are method only, and for `food processor` are method or null.
These rare terms do not set the main evaluation priority.

`prompt_example` identifies terms explicitly used as examples in the prompt.
The report counts failures on the other terms separately. Neither sample
estimates accuracy across the full library.

Run from `backend/`, with the usual application AI configuration:

```sh
uv run python -m scripts.eval_keyword_classification --output /tmp/keyword-quality.json
```

Use `--model gemini-2.5-flash` to compare another model on the configured provider.
The command makes real AI calls. Database writes are blocked with SQLite
`query_only`; only the JSON report is written. The report includes prompt and
sample hashes, all expected and actual labels, errors, tokens, and cost.

The default run shuffles the same sample into ten-keyword batches on three
repeats. Any wrong label, false category assignment, or response error makes the
command exit with status 1. `accepted` labels are equally valid. The report keeps
failures and use counts so review can prioritise frequent keywords rather than
treat every disagreement as equally important.
