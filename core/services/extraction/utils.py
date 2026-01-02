import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def build_image_path_lookup(epub_path: Path) -> dict[str, list[str]]:
    cache = {}
    try:
        with zipfile.ZipFile(epub_path, "r") as epub:
            for file_path in epub.namelist():
                if file_path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                    filename = Path(file_path).name.lower()
                    if filename not in cache:
                        cache[filename] = []
                    cache[filename].append(file_path)
    except Exception as e:
        logger.error(f"Error building image cache for {epub_path}: {e}")
    return cache


def resolve_image_path_in_epub(
    relative_image_path: str | None, image_cache: dict[str, list[str]]
) -> str | None:
    if not relative_image_path:
        return None

    filename = Path(relative_image_path).name.lower()
    matches = image_cache.get(filename, [])

    if not matches:
        return None

    if len(matches) == 1:
        return matches[0]

    relative_lower = relative_image_path.lower()
    for match in matches:
        if match.lower().endswith(relative_lower):
            return match

    logger.warning(f"Multiple matches for {filename}, using first: {matches[0]}")
    return matches[0]


def deduplicate_recipes_by_title(recipes: list) -> list:
    seen_titles = set()
    unique_recipes = []
    for recipe in recipes:
        title_key = recipe.name.lower().strip()
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_recipes.append(recipe)
        else:
            logger.debug(f"Deduplicating recipe: {recipe.name}")
    return unique_recipes
