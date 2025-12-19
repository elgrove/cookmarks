import csv
import json
import time
from pathlib import Path
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.forms.models import model_to_dict

from core.models import Book, Config, ExtractionReport
from core.services.extract import extract_recipe_data_from_book

EVAL_DIR = settings.BASE_DIR / "_eval"
RESULTS_CSV = EVAL_DIR / "results.csv"


EVAL_PROVIDER = "GEMINI"
EVAL_PROVIDER_KEY = "AIzaSyDwZrVbEVLGobdJTxMbEcM7oeGbZYb6-l4"
# EVAL_PROVIDER = "OPENROUTER"
# EVAL_PROVIDER_KEY = (
#     "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"
# )
EVAL_MODEL = "gemini-2.5-flash-lite"
# EVAL_MODEL =  'openai/gpt-oss-120b'
# EVAL_MODEL =  'nousresearch/hermes-4-405b'
EVAL_CONFIG = {
    "Craveable_ All I Want to Eat, Big Flavours for Every Mood (751)": {
        "provider": EVAL_PROVIDER,
        "model": EVAL_MODEL,
        "api_key": EVAL_PROVIDER_KEY,
    },
    # "Nothing Fancy_ Unfussy Food for Having People Over (227)": {
    #     "provider": EVAL_PROVIDER,
    #     "model": EVAL_MODEL,
    #     "api_key": EVAL_PROVIDER_KEY,
    # },
    # "The Curry Guy_ Recreate Over 100 of the Best British Indian Restaurant Recipes at Home (502)": {
    #     "provider": EVAL_PROVIDER,
    #     "model": EVAL_MODEL,
    #     "api_key": EVAL_PROVIDER_KEY,
    # },
}


EVAL_RATE_LIMIT = 256


class Command(BaseCommand):
    help = "Run evaluation suite on books in _eval folder"

    def get_eval_books(self):
        books = []
        for book_name in EVAL_CONFIG.keys():
            book_dir = EVAL_DIR / book_name
            if book_dir.is_dir():
                gold_recipes_path = book_dir / "_cookmarks" / "recipes.json"
                if gold_recipes_path.exists():
                    books.append(book_dir)
        return books

    def load_gold_recipes(self, book_dir: Path):
        gold_path = book_dir / "_cookmarks" / "recipes.json"
        with open(gold_path, "r") as f:
            return json.load(f)

    def compute_jaccard(self, set1: set, set2: set) -> float:
        if not set1 and not set2:
            return 1.0
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    def score_recipe(self, predicted: dict, gold: dict) -> dict:
        scores = {}

        pred_name = predicted.get("name", "")
        gold_name = gold.get("name", "")
        pred_tokens = set(pred_name.lower().split())
        gold_tokens = set(gold_name.lower().split())
        scores["name_f1"] = self.compute_jaccard(pred_tokens, gold_tokens)

        pred_ingredients = set(predicted.get("recipeIngredients", []))
        gold_ingredients = set(gold.get("recipeIngredients", []))
        scores["ingredients_jaccard"] = self.compute_jaccard(
            pred_ingredients, gold_ingredients
        )
        scores["ingredients_missing"] = len(gold_ingredients - pred_ingredients)
        scores["ingredients_extra"] = len(pred_ingredients - gold_ingredients)

        pred_steps = set(predicted.get("recipeInstructions", []))
        gold_steps = set(gold.get("recipeInstructions", []))
        scores["steps_jaccard"] = self.compute_jaccard(pred_steps, gold_steps)
        scores["steps_missing"] = len(gold_steps - pred_steps)
        scores["steps_extra"] = len(pred_steps - gold_steps)

        pred_yield = predicted.get("recipeYield", "")
        gold_yield = gold.get("recipeYield", "")
        scores["yield_match"] = 1.0 if pred_yield.lower() == gold_yield.lower() else 0.0

        pred_image = predicted.get("image", "")
        gold_image = gold.get("image", "")
        if not gold_image:
            scores["image_match"] = None
        else:
            scores["image_match"] = 1.0 if pred_image == gold_image else 0.0

        pred_keywords = set(predicted.get("keywords", []))
        gold_keywords = set(gold.get("keywords", []))
        if not gold_keywords:
            scores["keywords_jaccard"] = 1.0 if not pred_keywords else 0.5
        else:
            scores["keywords_jaccard"] = self.compute_jaccard(
                pred_keywords, gold_keywords
            )
        scores["keywords_overlap"] = len(pred_keywords & gold_keywords)

        composite_sum = (
            0.30 * scores["ingredients_jaccard"]
            + 0.30 * scores["steps_jaccard"]
            + 0.20 * scores["name_f1"]
            + 0.15 * scores["yield_match"]
        )
        composite_weight = 0.95

        if scores["image_match"] is not None:
            composite_sum += 0.05 * scores["image_match"]
            composite_weight += 0.05

        scores["composite"] = composite_sum / composite_weight

        return scores

    def aggregate_scores(self, recipe_scores: list[dict]) -> dict:
        if not recipe_scores:
            return {}

        agg = {}
        keys = recipe_scores[0].keys()

        numeric_keys = [
            "name_f1",
            "ingredients_jaccard",
            "ingredients_missing",
            "ingredients_extra",
            "steps_jaccard",
            "steps_missing",
            "steps_extra",
            "yield_match",
            "image_match",
            "keywords_jaccard",
            "keywords_overlap",
            "composite",
        ]

        for key in keys:
            if key not in numeric_keys:
                continue
            values = [s[key] for s in recipe_scores if s.get(key) is not None]

            if not values:
                agg[f"{key}_mean"] = None
                agg[f"{key}_median"] = None
                continue

            agg[f"{key}_mean"] = sum(values) / len(values)
            sorted_values = sorted(values)
            median_idx = len(sorted_values) // 2
            agg[f"{key}_median"] = sorted_values[median_idx]

        return agg

    def save_run_results(
        self,
        model: str,
        provider: str,
        book_dir: Path,
        predicted_recipes: list[dict],
        gold_recipes: list[dict],
        recipe_scores: list[dict],
        metrics: dict,
        report: ExtractionReport,
        duration: float,
        run_timestamp: str,
    ):
        run_dir = (
            EVAL_DIR / "runs" / f"{provider}_{model}" / run_timestamp / book_dir.name
        )
        run_dir.mkdir(parents=True, exist_ok=True)

        with open(run_dir / "predicted_recipes.json", "w") as f:
            json.dump(predicted_recipes, f, indent=2, ensure_ascii=False)

        with open(run_dir / "recipe_scores.json", "w") as f:
            json.dump(recipe_scores, f, indent=2, ensure_ascii=False)

        with open(run_dir / "report.json", "w") as f:
            json.dump(
                model_to_dict(report), f, indent=2, ensure_ascii=False, default=str
            )

        summary = {
            "model": model,
            "provider": provider,
            "book": book_dir.name,
            "timestamp": run_timestamp,
            "duration_seconds": duration,
            "num_gold_recipes": len(gold_recipes),
            "num_predicted_recipes": len(predicted_recipes),
            "num_matched_recipes": len(recipe_scores),
            "metrics": metrics,
        }

        with open(run_dir / "summary.json", "w") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        return summary

    def append_to_csv(self, summaries: list[dict]):
        file_exists = RESULTS_CSV.exists()

        fieldnames = [
            "timestamp",
            "provider",
            "model",
            "book",
            "duration_seconds",
            "num_gold_recipes",
            "num_predicted_recipes",
            "num_matched_recipes",
            "recall",
            "composite_mean",
            "composite_median",
            "name_f1_mean",
            "ingredients_jaccard_mean",
            "ingredients_missing_mean",
            "ingredients_extra_mean",
            "steps_jaccard_mean",
            "steps_missing_mean",
            "steps_extra_mean",
            "yield_match_mean",
            "image_match_mean",
            "keywords_jaccard_mean",
            "keywords_overlap_mean",
        ]

        with open(RESULTS_CSV, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()

            for summary in summaries:
                row = {
                    "timestamp": summary["timestamp"],
                    "provider": summary["provider"],
                    "model": summary["model"],
                    "book": summary["book"],
                    "duration_seconds": summary["duration_seconds"],
                    "num_gold_recipes": summary["num_gold_recipes"],
                    "num_predicted_recipes": summary["num_predicted_recipes"],
                    "num_matched_recipes": summary["num_matched_recipes"],
                    "recall": summary["metrics"].get("recall", ""),
                    "composite_mean": summary["metrics"].get("composite_mean", ""),
                    "composite_median": summary["metrics"].get("composite_median", ""),
                    "name_f1_mean": summary["metrics"].get("name_f1_mean", ""),
                    "ingredients_jaccard_mean": summary["metrics"].get(
                        "ingredients_jaccard_mean", ""
                    ),
                    "ingredients_missing_mean": summary["metrics"].get(
                        "ingredients_missing_mean", ""
                    ),
                    "ingredients_extra_mean": summary["metrics"].get(
                        "ingredients_extra_mean", ""
                    ),
                    "steps_jaccard_mean": summary["metrics"].get(
                        "steps_jaccard_mean", ""
                    ),
                    "steps_missing_mean": summary["metrics"].get(
                        "steps_missing_mean", ""
                    ),
                    "steps_extra_mean": summary["metrics"].get("steps_extra_mean", ""),
                    "yield_match_mean": summary["metrics"].get("yield_match_mean", ""),
                    "image_match_mean": summary["metrics"].get("image_match_mean", ""),
                    "keywords_jaccard_mean": summary["metrics"].get(
                        "keywords_jaccard_mean", ""
                    ),
                    "keywords_overlap_mean": summary["metrics"].get(
                        "keywords_overlap_mean", ""
                    ),
                }
                writer.writerow(row)

    def handle(self, *args, **options):
        eval_books = self.get_eval_books()

        run_timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        all_summaries = []

        for book_dir in eval_books:
            book_config = EVAL_CONFIG[book_dir.name]
            model = book_config["model"]
            provider = book_config["provider"]
            api_key = book_config["api_key"]

            config = Config.get_solo()
            config.ai_provider = provider
            if provider == 'GEMINI':
                config.gemini_model = model
                config.gemini_api_key = api_key
            elif provider == 'OPENROUTER':
                config.openrouter_model = model
                config.openrouter_api_key = api_key            
            config.extraction_rate_limit_per_minute = EVAL_RATE_LIMIT
            config.image_matching_sample_size = 10
            config.save()

            gold_recipes = self.load_gold_recipes(book_dir)

            book, _ = Book.objects.get_or_create(
                path=str(book_dir),
                defaults={
                    "title": book_dir.name,
                    "author": "Eval Author",
                    "calibre_id": 99990 + hash(book_dir.name) % 1000,
                },
            )

            start_time = time.time()
            recipes, report = extract_recipe_data_from_book(book)
            duration = time.time() - start_time

            predicted_recipes = [r.model_dump() for r in recipes]

            gold_by_order = {r.get("book_order"): r for r in gold_recipes}
            pred_by_order = {r.get("book_order"): r for r in predicted_recipes}

            recipe_scores = []
            for order, gold in gold_by_order.items():
                pred = pred_by_order.get(order)
                if pred:
                    score = self.score_recipe(pred, gold)
                    score["recipe_name"] = gold.get("name", "Unknown")
                    score["book_order"] = order
                    recipe_scores.append(score)

            metrics = self.aggregate_scores(recipe_scores)
            metrics["num_gold_recipes"] = len(gold_recipes)
            metrics["num_predicted_recipes"] = len(predicted_recipes)
            metrics["num_matched_recipes"] = len(recipe_scores)
            metrics["recall"] = (
                len(recipe_scores) / len(gold_recipes) if gold_recipes else 0.0
            )

            summary = self.save_run_results(
                model,
                provider,
                book_dir,
                predicted_recipes,
                gold_recipes,
                recipe_scores,
                metrics,
                report,
                duration,
                run_timestamp,
            )
            all_summaries.append(summary)

        self.append_to_csv(all_summaries)
