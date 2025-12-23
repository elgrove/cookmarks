import base64
import logging
import os
import random
import re
import zipfile
from pathlib import Path

from lxml import etree  # type: ignore

logger = logging.getLogger(__name__)

SEPARATE_IMAGE_CHAPTERS_THRESHOLD = 150
MANY_RECIPES_PER_FILE_THRESHOLD = 20
IMAGE_MATCHING_SAMPLE_SIZE = 10
CHAPTER_BLOCK_COUNT = 16


def get_chapterlike_files_from_epub(epub_path: Path) -> list[str]:
    """
    Extracts chapter-like files from an EPUB.
    """
    try:
        with zipfile.ZipFile(epub_path, "r") as epub:
            container_xml = epub.read("META-INF/container.xml")
            container_tree = etree.fromstring(container_xml)
            opf_path = container_tree.xpath("string(//*[local-name()='rootfile']/@full-path)")

            if not opf_path:
                try:
                    opf_path = [name for name in epub.namelist() if name.endswith(".opf")][0]
                except IndexError:
                    logger.error(f"Could not find OPF file in {epub_path}")
                    return []

            opf_xml = etree.fromstring(epub.read(opf_path))

            default_ns = opf_xml.nsmap.get(None)
            if default_ns:
                ns = {"opf": default_ns}
                manifest_items = opf_xml.xpath("//opf:manifest/opf:item", namespaces=ns)
                spine_refs = opf_xml.xpath(
                    "//opf:spine/opf:itemref[not(@linear) or @linear!='no']", namespaces=ns
                )
            else:
                manifest_items = opf_xml.xpath("//manifest/item")
                spine_refs = opf_xml.xpath("//spine/itemref[not(@linear) or @linear!='no']")

            manifest = {
                i.get("id"): {
                    "href": i.get("href"),
                    "media": i.get("media-type"),
                    "props": (i.get("properties") or ""),
                }
                for i in manifest_items
            }
            spine_ids = [i.get("idref") for i in spine_refs]

            base = os.path.dirname(opf_path)
            spine_files = [
                os.path.join(base, manifest[sid]["href"])
                for sid in spine_ids
                if manifest.get(sid)
                and manifest[sid]["media"] in ("application/xhtml+xml", "application/x-dtbook+xml")
                and "nav" not in manifest[sid]["props"]
            ]

            chapter_like_pattern = r"p\d+|ch[_-]?\d[\d_-]*|(chapter|part)\d|chapter|part|_?c\d+"
            ignore_pattern = r"(toc|nav|cover|copyright|dedication|acknowledg|appendix)"

            chapter_like_files = [
                f
                for f in spine_files
                if re.search(chapter_like_pattern, os.path.basename(f), re.I)
                and not re.search(ignore_pattern, os.path.basename(f), re.I)
            ]

            if len(chapter_like_files) <= 4:
                logger.warning(
                    f"Too few chapter-like files ({len(chapter_like_files)}) found for {epub_path}, returning all spine files."
                )
                chapter_like_files = [
                    f
                    for f in spine_files
                    if not re.search(ignore_pattern, os.path.basename(f), re.I)
                ]

            return chapter_like_files

    except Exception as e:
        logger.error(f"Error processing {epub_path}: {e}", exc_info=True)
        return []


def extract_image_from_epub(
    epub_path: Path, image_ref: str, opf_base_path: str | None = None
) -> str:
    if not image_ref:
        return ""

    try:
        with zipfile.ZipFile(epub_path, "r") as epub:
            if opf_base_path is None:
                container_xml = epub.read("META-INF/container.xml")
                container_tree = etree.fromstring(container_xml)
                opf_path = container_tree.xpath("string(//*[local-name()='rootfile']/@full-path)")
                opf_base_path = os.path.dirname(opf_path)

            image_path = os.path.normpath(os.path.join(opf_base_path, image_ref))
            image_basename = os.path.basename(image_ref)

            try:
                image_data = epub.read(image_path)
            except KeyError:
                possible_paths = [image_ref, image_path]

                for name in epub.namelist():
                    if name.endswith("/" + image_basename) or name == image_basename:
                        possible_paths.append(name)

                for path in possible_paths:
                    try:
                        image_data = epub.read(path)
                        break
                    except KeyError:
                        continue
                else:
                    logger.warning(f"Image not found in EPUB: {image_ref}")
                    return ""

            ext = os.path.splitext(image_ref)[1].lower()
            mime_type = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }.get(ext, "image/jpeg")

            base64_data = base64.b64encode(image_data).decode("utf-8")
            return f"data:{mime_type};base64,{base64_data}"

    except Exception as e:
        logger.error(f"Error extracting image {image_ref} from {epub_path}: {e}")
        return ""


def has_separate_image_chapters(chapter_files: list[str]) -> bool:
    return len(chapter_files) > SEPARATE_IMAGE_CHAPTERS_THRESHOLD


def get_sample_chapters_content(epub_path: Path, chapter_files: list[str]) -> str:
    # take sample from middle 50% of the book
    total_chapters = len(chapter_files)
    mid_start = int(total_chapters * 0.25)
    mid_end = int(total_chapters * 0.75)
    mid_len = mid_end - mid_start

    if total_chapters <= IMAGE_MATCHING_SAMPLE_SIZE:
        sample_files = chapter_files
    elif mid_len <= IMAGE_MATCHING_SAMPLE_SIZE:
        sample_files = chapter_files[mid_start:mid_end]
    else:
        max_start = mid_len - IMAGE_MATCHING_SAMPLE_SIZE
        start_idx = random.randint(0, max_start) + mid_start
        sample_files = chapter_files[start_idx : start_idx + IMAGE_MATCHING_SAMPLE_SIZE]

    contents = []
    try:
        with zipfile.ZipFile(epub_path, "r") as epub:
            for file_path in sample_files:
                try:
                    html_content = epub.read(file_path).decode("utf-8")
                    contents.append(f"--- FILE: {os.path.basename(file_path)} ---\n{html_content}")
                except Exception as e:
                    logger.warning(f"Could not read {file_path}: {e}")
                    continue
    except Exception as e:
        logger.error(f"Error reading sample chapters from {epub_path}: {e}")

    return "\n\n".join(contents)


def split_chapters_into_blocks(chapter_files: list[str]) -> list[list[str]]:
    if len(chapter_files) <= CHAPTER_BLOCK_COUNT:
        return [chapter_files]

    block_size = len(chapter_files) // CHAPTER_BLOCK_COUNT
    blocks = []

    for i in range(CHAPTER_BLOCK_COUNT):
        start_idx = i * block_size
        if i == CHAPTER_BLOCK_COUNT - 1:
            end_idx = len(chapter_files)
        else:
            end_idx = start_idx + block_size + 1

        blocks.append(chapter_files[start_idx:end_idx])

    return blocks


def get_block_content(epub_path: Path, chapter_files: list[str]) -> str:
    contents = []
    try:
        with zipfile.ZipFile(epub_path, "r") as epub:
            for file_path in chapter_files:
                try:
                    html_content = epub.read(file_path).decode("utf-8")
                    contents.append(html_content)
                except Exception as e:
                    logger.warning(f"Could not read {file_path}: {e}")
                    continue
    except Exception as e:
        logger.error(f"Error reading block content from {epub_path}: {e}")

    return "\n\n".join(contents)
