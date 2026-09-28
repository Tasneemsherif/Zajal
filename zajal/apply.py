"""Open the marked-up artwork, apply the corrections, write a clean PDF."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from .document import PAGE_CENTRE, Page, read_page, render_page
from .edits import EXTRA_GLYPHS, PAGES
from .fonts import ArabicFont, FallbackLatinFont, LatinFont
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artwork" / "zajal-labels-markup.pdf"
DEFAULT_OUT = ROOT / "dist" / "zajal-labels.pdf"
FALLBACK_SERIF = "/usr/share/fonts/truetype/croscore/Tinos-Regular.ttf"
CREAM = (1.0, 0.965, 0.898)


def _latin_font(doc: pymupdf.Document) -> LatinFont:
    xref = next(f[0] for f in doc[0].get_fonts(full=True)
                if "Plantagenet" in f[3])
    return LatinFont(doc, xref)


def _arabic_font(doc: pymupdf.Document) -> ArabicFont:
    xref = next(f[0] for f in doc[0].get_fonts(full=True)
                if "Guesswhat" in f[3])
    font = ArabicFont(doc, xref)
    font.ensure_encoded(EXTRA_GLYPHS)
    return font


LATIN_MEASURE = 460.0


def _centre_latin(page: Page, latin: LatinFont, fallback: FallbackLatinFont) -> None:
    line = page.latin
    if line is None:
        return
    font = fallback if line.fallback else latin
    if line.fallback:
        while line.width(font) > LATIN_MEASURE and line.size > 22:
            line.size *= 0.92
            line.tracking *= 0.92
    line.x = PAGE_CENTRE - line.width(font) / 2


def _draw_fallback(pdf_page: pymupdf.Page, page: Page, fallback: FallbackLatinFont) -> None:
    line = page.latin
    if line is None or not line.fallback:
        return
    x = line.x
    y_top = 792.0 - line.y
    for i, ch in enumerate(line.text):
        pdf_page.insert_text(
            pymupdf.Point(x, y_top),
            ch,
            fontfile=fallback.path,
            fontsize=line.size,
            color=CREAM,
        )
        x += fallback.text_width(ch, line.size)
        if i < len(line.text) - 1:
            x += line.tracking


def apply(source: Path = SOURCE, dest: Path = DEFAULT_OUT) -> Path:
    doc = pymupdf.open(source)
    arabic = _arabic_font(doc)
    latin = _latin_font(doc)
    fallback = FallbackLatinFont(FALLBACK_SERIF)

    from . import document as document_mod
    document_mod._ARABIC_FONT = arabic

    for index, edit in enumerate(PAGES):
        page = read_page(doc, index, latin)
        edit(page, arabic)
        if page.latin_changed:
            _centre_latin(page, latin, fallback)
        stream = render_page(page, arabic, latin)
        xrefs = doc[index].get_contents()
        if len(xrefs) != 1:
            raise RuntimeError(f"page {index + 1} has {len(xrefs)} content streams")
        doc.update_stream(xrefs[0], stream)
        _draw_fallback(doc[index], page, fallback)

    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest, garbage=4, deflate=True)
    doc.close()
    return dest


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=SOURCE)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    path = apply(args.source, args.output)
    print(path)


if __name__ == "__main__":
    main()
