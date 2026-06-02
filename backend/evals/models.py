"""Typed result models for the eval suite.

`FieldScores` / `RecipeScore` / `BookResult` are the rich per-run artefacts written
under ``runs/``. `LedgerRecord` is the flat, one-line-per-(run, model, book) row
appended to ``index.jsonl`` for cross-run comparison.
"""

from pydantic import BaseModel


class CandidateModel(BaseModel):
    """One model evaluated for a task: a (provider, model) pair, e.g. parsed from the
    config shorthand ``"GEMINI:gemini-2.5-flash-lite"``."""

    provider: str
    model: str

    @property
    def id(self) -> str:
        return f"{self.provider}:{self.model}"

    @classmethod
    def parse(cls, spec: str) -> "CandidateModel":
        provider, _, model = spec.partition(":")
        if not provider or not model:
            raise ValueError(f"Model must be 'PROVIDER:model', got {spec!r}")
        return cls(provider=provider, model=model)


class TaskSpec(BaseModel):
    """A pipeline task (ModelRole value) and the candidate models to evaluate for it,
    run against the books that exercise it."""

    role: str
    books: list[str]
    models: list[CandidateModel]


class BookSpec(BaseModel):
    slug: str
    calibre_id: int
    gold: str
    has_photos: bool = True


class FieldScores(BaseModel):
    """Per-field fidelity for one matched (gold, predicted) recipe pair. `image_match`
    is None when the gold recipe has no image, so it never drags an average down."""

    name_similarity: float
    ingredients_jaccard: float
    ingredients_missing: int
    ingredients_extra: int
    instructions_jaccard: float
    instructions_missing: int
    instructions_extra: int
    yield_match: float
    image_match: float | None
    keywords_jaccard: float
    composite: float


class RecipeScore(BaseModel):
    """One gold recipe's outcome: matched to a prediction (with field scores) or missed."""

    gold_name: str
    predicted_name: str | None
    matched: bool
    match_score: float | None
    scores: FieldScores | None


class BookResult(BaseModel):
    """Everything scored for one (model, book): recipe-set retrieval metrics, aggregated
    field means, cost/latency, and the per-recipe drill-down."""

    book: str
    num_gold: int
    num_predicted: int
    num_matched: int
    precision: float
    recall: float
    f1: float
    metrics: dict[str, float]
    cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    duration_s: float
    extraction_method: str | None
    recipe_scores: list[RecipeScore]
    hallucinated: list[str]


class LedgerRecord(BaseModel):
    """A flat row in ``index.jsonl`` — the unit of cross-run history, one per
    (run, task, model, book)."""

    run_id: str
    timestamp: str
    git_sha: str | None
    task: str
    model_id: str
    provider: str
    model: str
    book: str
    num_gold: int
    num_predicted: int
    num_matched: int
    precision: float
    recall: float
    f1: float
    composite_mean: float
    ingredients_jaccard_mean: float
    instructions_jaccard_mean: float
    cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    duration_s: float
