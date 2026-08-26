"""Eval suites.

**Extraction** (:mod:`evals.runner`) runs the real recipe-extraction pipeline against hand-curated gold cookbooks and
scores the output: recipe-set precision/recall/F1 plus per-field fidelity, cost and
latency. Results are appended to a ledger (``index.jsonl``) so a model's quality can
be tracked across runs and code versions.

**Assistant** (:mod:`evals.assistant`) runs the real chat agent, tools and all, against
a throwaway copy of the app database and scores the transcript: which tools it reached
for, how many searches it tried, and whether the recipes it linked are ones a tool
actually returned.

This package has no import-time side effects. The runner binds the pipeline to an
isolated eval database explicitly (see :mod:`evals.environment`); importing the pure
scoring modules (:mod:`evals.matching`, :mod:`evals.metrics`) touches nothing.
"""
