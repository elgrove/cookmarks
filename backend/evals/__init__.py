"""Extraction eval suite.

Runs the real recipe-extraction pipeline against hand-curated gold cookbooks and
scores the output: recipe-set precision/recall/F1 plus per-field fidelity, cost and
latency. Results are appended to a ledger (``index.jsonl``) so a model's quality can
be tracked across runs and code versions.

This package has no import-time side effects. The runner binds the pipeline to an
isolated eval database explicitly (see :mod:`evals.environment`); importing the pure
scoring modules (:mod:`evals.matching`, :mod:`evals.metrics`) touches nothing.
"""
