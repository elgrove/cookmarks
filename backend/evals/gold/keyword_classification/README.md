# Keyword classification quality

`keywords.json` contains 65 reference labels: 32 clear category matches and 33
terms that must remain uncategorised. These are agent-authored expectations based
on the category definitions and the user's requirement to classify only strong
fits. Review the expectations before using them as a production release gate.

`prompt_example` identifies terms explicitly used as examples in the prompt.
The report counts failures on the other terms separately. This sample tests
specific category boundaries; it does not estimate accuracy across the library.

Equipment, duration, convenience, vague descriptions, and occasions have no
category. `brine` also has no category because the keyword alone does not tell us
whether it names an ingredient or a technique. `braising` clearly names a method.

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
command exit with status 1. Exact-label agreement is a strict gate; false
assignments and missed clear matches can also be reviewed separately.
