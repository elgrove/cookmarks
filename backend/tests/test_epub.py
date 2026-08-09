import zipfile
from pathlib import Path

import pytest

from app.services.epub import get_chapterlike_files_from_epub

CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

DEFAULT_NS_OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="c1" href="chapter01.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="chapter02.xhtml" media-type="application/xhtml+xml"/>
    <item id="img" href="cover.jpg" media-type="image/jpeg"/>
  </manifest>
  <spine>
    <itemref idref="nav"/>
    <itemref idref="c1"/>
    <itemref idref="c2"/>
  </spine>
</package>
"""

PREFIXED_NS_OPF = """<?xml version="1.0"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf"
             xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
  <opf:manifest>
    <opf:item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <opf:item id="c1" href="chapter01.xhtml" media-type="application/xhtml+xml"/>
    <opf:item id="c2" href="chapter02.xhtml" media-type="application/xhtml+xml"/>
    <opf:item id="img" href="cover.jpg" media-type="image/jpeg"/>
  </opf:manifest>
  <opf:spine>
    <opf:itemref idref="nav"/>
    <opf:itemref idref="c1"/>
    <opf:itemref idref="c2"/>
  </opf:spine>
</opf:package>
"""

NO_NS_OPF = """<?xml version="1.0"?>
<package version="2.0">
  <manifest>
    <item id="c1" href="chapter01.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="chapter02.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="c1"/>
    <itemref idref="c2"/>
  </spine>
</package>
"""


def _write_epub(path: Path, opf: str) -> Path:
    with zipfile.ZipFile(path, "w") as epub:
        epub.writestr("mimetype", "application/epub+zip")
        epub.writestr("META-INF/container.xml", CONTAINER_XML)
        epub.writestr("OEBPS/content.opf", opf)
        for name in ("nav.xhtml", "chapter01.xhtml", "chapter02.xhtml"):
            epub.writestr(f"OEBPS/{name}", "<html/>")
    return path


@pytest.mark.parametrize(
    "opf", [DEFAULT_NS_OPF, PREFIXED_NS_OPF, NO_NS_OPF], ids=["default-ns", "prefixed-ns", "no-ns"]
)
def test_reads_the_spine_however_the_opf_declares_its_namespace(tmp_path: Path, opf: str) -> None:
    epub = _write_epub(tmp_path / "book.epub", opf)

    assert get_chapterlike_files_from_epub(epub) == [
        "OEBPS/chapter01.xhtml",
        "OEBPS/chapter02.xhtml",
    ]


def test_corrupt_epub_reads_as_no_chapters(tmp_path: Path) -> None:
    not_a_zip = tmp_path / "book.epub"
    not_a_zip.write_bytes(b"BOOKMOBI not a zip at all")

    assert get_chapterlike_files_from_epub(not_a_zip) == []
