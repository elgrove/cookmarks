"""Preview or apply the flat-keyword backfill for existing recipes.

This script derives tags from retained enrichment facts and original extraction
keywords. Applying changes also updates semantic-search embeddings by default.

    cd backend && uv run python -m scripts.backfill_recipe_keywords \\
        --dry-run --sample 20 --legacy-db /path/to/pre-enrichment.sqlite3
    cd backend && uv run python -m scripts.backfill_recipe_keywords \\
        --apply --legacy-db /path/to/pre-enrichment.sqlite3
"""

import argparse
import random
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, joinedload, selectinload, sessionmaker

from app.db import SessionLocal
from app.models.enums import RecipeEnrichmentStatus
from app.models.ingredient import RecipeIngredient
from app.models.recipe import Recipe
from app.models.recipe_enrichment import RecipeEnrichmentState
from app.models.recipe_fact import RecipeFacet
from app.services.ai import resolve_embeddings
from app.services.embeddings import embed_recipes
from app.services.keyword_backfill import KeywordProposal, cuisine_display_names, propose_keywords
from app.services.keywords import get_or_create_keyword


def _recipes(session: Session, recipe_ids: Iterable[object]) -> list[Recipe]:
    return list(
        session.scalars(
            select(Recipe)
            .where(Recipe.id.in_(recipe_ids))
            .options(
                joinedload(Recipe.book),
                selectinload(Recipe.keywords),
                selectinload(Recipe.ingredients).joinedload(RecipeIngredient.canonical_ingredient),
                selectinload(Recipe.facets).joinedload(RecipeFacet.facet_value),
                selectinload(Recipe.cuisines),
            )
        )
    )


def _sample_ids(session: Session, sample: int, seed: int) -> list[object]:
    ids = list(
        session.scalars(
            select(Recipe.id)
            .join(RecipeEnrichmentState)
            .where(RecipeEnrichmentState.status == RecipeEnrichmentStatus.COMPLETE)
            .order_by(Recipe.id)
        )
    )
    if sample > len(ids):
        raise ValueError(f"sample size {sample} exceeds {len(ids)} enriched recipes")
    return random.Random(seed).sample(ids, sample)


def _format(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "—"


def print_proposal(recipe: Recipe, proposal: KeywordProposal) -> None:
    book = recipe.book.title if recipe.book is not None else "Unknown book"
    print(f"{book} — {recipe.name}")
    print(f"  Original tags:   {_format(proposal.legacy_keywords)}")
    print(f"  Courses:         {_format(proposal.courses)}")
    print(f"  Cuisines:        {_format(proposal.cuisines)}")
    print(f"  Key ingredients: {_format(proposal.key_ingredients)}")
    print(f"  Primary method:  {_format(proposal.primary_methods)}")
    print(f"  Proposed:        {_format(proposal.keywords)}")
    print()


def _all_ids(session: Session) -> list[object]:
    return list(session.scalars(select(Recipe.id).order_by(Recipe.id)))


def _legacy_keywords(session: Session, recipe_ids: Iterable[object]) -> dict[object, list[str]]:
    recipes = list(
        session.scalars(
            select(Recipe).where(Recipe.id.in_(recipe_ids)).options(selectinload(Recipe.keywords))
        )
    )
    return {recipe.id: [keyword.name for keyword in recipe.keywords] for recipe in recipes}


def _legacy_recipe_ids(session: Session) -> set[object]:
    return set(session.scalars(select(Recipe.id)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report proposals without writing")
    parser.add_argument("--apply", action="store_true", help="replace recipe keyword sets")
    parser.add_argument("--sample", type=int, help="number of enriched recipes to show")
    parser.add_argument(
        "--legacy-db",
        type=Path,
        required=True,
        help="pre-enrichment SQLite backup that holds the original extraction keywords",
    )
    parser.add_argument(
        "--seed", type=int, default=191, help="random seed for --sample (default: 191)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=500, help="apply batch size (default: 500)"
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="do not update semantic-search vectors after changing keywords",
    )
    args = parser.parse_args()

    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run cannot be used together")
    if args.apply and args.sample is not None:
        parser.error("--sample is for dry runs only")
    if not args.apply and not args.dry_run:
        parser.error("choose --dry-run or --apply")
    if args.sample is not None and args.sample < 1:
        parser.error("--sample must be positive")
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")

    legacy_engine = create_engine(f"sqlite:///{args.legacy_db}")
    legacy_session_factory = sessionmaker(legacy_engine)
    labels = cuisine_display_names()
    with SessionLocal() as session, legacy_session_factory() as legacy_session:
        if args.dry_run:
            sample = args.sample or 20
            recipe_ids = _sample_ids(session, sample, args.seed)
            recipes = _recipes(session, recipe_ids)
            legacy = _legacy_keywords(legacy_session, recipe_ids)
            for recipe in sorted(recipes, key=lambda item: (item.book.title, item.name)):
                print_proposal(recipe, propose_keywords(recipe, legacy.get(recipe.id, []), labels))
            all_recipe_ids = _all_ids(session)
            all_legacy_ids = _legacy_recipe_ids(legacy_session)
            missing = sum(recipe.id not in legacy for recipe in recipes)
            missing_total = len(all_recipe_ids) - len(all_legacy_ids)
            print(
                f"Reviewed {len(recipes)} enriched recipe(s); {missing} had no original-tag record; "
                "no database changes made."
            )
            print(
                f"Full apply eligibility: {len(all_legacy_ids)} of {len(all_recipe_ids)} recipes; "
                f"{missing_total} original-tag record(s) missing."
            )
            return

        changed = 0
        embedded = 0
        recipe_ids = _all_ids(session)
        legacy = _legacy_keywords(legacy_session, recipe_ids)
        missing = [recipe_id for recipe_id in recipe_ids if recipe_id not in legacy]
        if missing:
            raise ValueError(
                f"{len(missing)} recipe(s) have no original-tag record in {args.legacy_db}; refusing to apply"
            )
        provider = None
        if not args.skip_embeddings:
            provider = resolve_embeddings(session)
            if provider is None or not provider.supports_embeddings:
                raise RuntimeError(
                    "no embedding-capable provider is configured; use --skip-embeddings only if "
                    "semantic-search vectors will be refreshed separately"
                )
        for start in range(0, len(recipe_ids), args.batch_size):
            recipes = _recipes(session, recipe_ids[start : start + args.batch_size])
            changed_recipes: list[Recipe] = []
            for recipe in recipes:
                proposal = propose_keywords(recipe, legacy[recipe.id], labels)
                current = {item.name for item in recipe.keywords}
                proposed = set(proposal.keywords)
                if current == proposed:
                    continue
                recipe.keywords = [
                    get_or_create_keyword(session, item) for item in proposal.keywords
                ]
                changed_recipes.append(recipe)
                changed += 1
            if changed_recipes and not args.skip_embeddings:
                assert provider is not None
                embedded += embed_recipes(session, changed_recipes, provider)
            session.commit()
            print(
                f"Committed recipes {start + 1}-{start + len(recipes)}; "
                f"changed {len(changed_recipes)}."
            )
        print(
            f"Updated {changed} of {len(recipe_ids)} recipe keyword set(s); "
            f"embedded {embedded} recipe(s)."
        )


if __name__ == "__main__":
    main()
