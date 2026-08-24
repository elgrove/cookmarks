import io
import logging
import zipfile
from collections import Counter
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.schemas.extraction import RecipeData

logger = logging.getLogger(__name__)

# Cookbook EPUBs carry page furniture — dietary icons, dingbats, chapter name-plates,
# rules set as images rather than markup — that the extractor happily attaches to a
# recipe. None of it is a dish photo, and all of it is either too small, the wrong
# shape, or repeated across the book.
MIN_SHORT_SIDE = 150
REUSED_SHORT_SIDE = 300
REUSE_LIMIT = 3
MIN_ASPECT_RATIO = 0.25
MAX_ASPECT_RATIO = 4.0
# A multi-panel step strip is a single wide image of numbered method photos, and is
# worth keeping despite its odd shape. Colour is what tells it from the typeset
# recipe title bars and line drawings that share those proportions: the strip is
# full of mid-tone colour, the title bar is black on white.
STRIP_MIN_WIDTH = 400
STRIP_MIN_SHORT_SIDE = 100
STRIP_MAX_ASPECT_RATIO = 6.0
STRIP_MIN_COLOURED_FRACTION = 0.2


def build_image_path_lookup(epub_path: Path) -> dict[str, list[str]]:
    """Index every image in the EPUB by its lowercased basename, so a recipe's
    (often relative) image reference can be resolved to a real archive path."""
    cache: dict[str, list[str]] = {}
    try:
        with zipfile.ZipFile(epub_path, "r") as epub:
            for file_path in epub.namelist():
                if file_path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                    filename = Path(file_path).name.lower()
                    cache.setdefault(filename, []).append(file_path)
    except Exception as e:
        logger.error(f"Error building image cache for {epub_path}: {e}")
    return cache


def resolve_image_path_in_epub(
    relative_image_path: str | None, image_cache: dict[str, list[str]]
) -> str | None:
    """Map a recipe's image reference to an actual path inside the EPUB, matching
    on basename and disambiguating multiple hits by the relative suffix."""
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


def _is_photographic(image: Image.Image) -> bool:
    hsv = image.convert("HSV").resize((32, 32))
    saturation = hsv.getchannel("S").tobytes()
    value = hsv.getchannel("V").tobytes()
    coloured = sum(1 for s, v in zip(saturation, value, strict=True) if s > 45 and 25 < v < 245)
    return coloured / 1024 >= STRIP_MIN_COLOURED_FRACTION


def find_decorative_images(epub_path: Path, members: list[str]) -> set[str]:
    """Of the images attached to a book's recipes, the ones that are page furniture
    rather than dish photos. Unreadable and missing members are rejected too, since
    they would only surface as a broken image. A book whose archive won't open keeps
    every image — a transient read failure must not strip a whole book."""
    if not members:
        return set()
    uses = Counter(members)
    decorative: set[str] = set()
    try:
        with zipfile.ZipFile(epub_path, "r") as epub:
            for member, count in uses.items():
                try:
                    with Image.open(io.BytesIO(epub.read(member))) as image:
                        width, height = image.size
                        short_side = min(width, height)
                        ratio = width / height if height else 0.0
                        step_strip = (
                            width >= STRIP_MIN_WIDTH
                            and short_side >= STRIP_MIN_SHORT_SIDE
                            and ratio <= STRIP_MAX_ASPECT_RATIO
                            and _is_photographic(image)
                        )
                except (KeyError, OSError, UnidentifiedImageError, ValueError):
                    decorative.add(member)
                    continue
                reused_small = short_side < REUSED_SHORT_SIDE and count >= REUSE_LIMIT
                odd_shape = (
                    short_side < MIN_SHORT_SIDE
                    or not MIN_ASPECT_RATIO <= ratio <= MAX_ASPECT_RATIO
                )
                if reused_small or (odd_shape and not step_strip):
                    decorative.add(member)
    except (zipfile.BadZipFile, OSError) as e:
        logger.error(f"Cannot screen images in {epub_path}, keeping all: {e}")
        return set()
    return decorative


def deduplicate_recipes_by_title(recipes: list[RecipeData]) -> list[RecipeData]:
    seen_titles: set[str] = set()
    unique_recipes: list[RecipeData] = []
    for recipe in recipes:
        title_key = recipe.name.lower().strip()
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_recipes.append(recipe)
        else:
            logger.debug(f"Deduplicating recipe: {recipe.name}")
    return unique_recipes
