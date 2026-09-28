"""Positioning helpers for Arabic glyphs and diacritics.

The source artwork places every mark by hand, but it does so consistently:
a mark is centred on its base letter and stacked above (or below) whatever is
already there with a small optical gap. These helpers reproduce that so added
marks sit like the ones the designer set.
"""

from __future__ import annotations

from .document import PAGE_CENTRE, Glyph
from .fonts import ArabicFont

GAP_ABOVE = 8.0
GAP_BELOW = 3.0
WORD_SPACE = 150.0  # font units


def ink_extent(glyphs: list[Glyph], font: ArabicFont) -> tuple[float, float]:
    boxes = [g.ink(font) for g in glyphs]
    return min(b[0] for b in boxes), max(b[2] for b in boxes)


def centre(glyphs: list[Glyph], font: ArabicFont, axis: float = PAGE_CENTRE) -> None:
    x0, x1 = ink_extent(glyphs, font)
    shift = axis - (x0 + x1) / 2
    for g in glyphs:
        g.x += shift


def attach(page_glyphs: list[Glyph], font: ArabicFont, base: Glyph, mark: str,
           side: str = "above", gap: float | None = None, dx: float = 0.0,
           size: float = 1.0) -> Glyph:
    """Build a diacritic glyph sitting above/below ``base``, clear of its neighbours.

    ``size`` scales the mark relative to the base letter, which is needed for
    the hamza: the subset only carries the full-size standalone ء.
    """
    gap = gap if gap is not None else (GAP_ABOVE if side == "above" else GAP_BELOW)
    box = font.box[mark]
    mark_size = base.size * size
    scale = mark_size / 1000.0
    bx0, btop, bx1, bbottom = base.ink(font)

    stacked = [g.ink(font) for g in page_glyphs
               if g is not base and font.is_mark(g.name)
               and g.ink(font)[0] < bx1 and g.ink(font)[2] > bx0]
    if side == "above":
        limit = min([btop] + [i[1] for i in stacked if i[3] <= btop + 1])
        y = 792 - (limit - gap) - box.y0 * scale
    else:
        limit = max([bbottom] + [i[3] for i in stacked if i[1] >= bbottom - 1])
        y = 792 - (limit + gap) - box.y1 * scale

    x = (bx0 + bx1) / 2 + dx - box.cx * scale
    return Glyph(mark, x, y, mark_size)


def lay_out(spec, size: float, baseline: float, font: ArabicFont) -> list[Glyph]:
    """Turn a declarative word description into positioned glyphs.

    ``spec`` lists base letters in visual order (left to right, the order the
    PDF paints them), each with the marks that hang off it::

        [("lam-ar", []), ("tah-ar.medi", [("dotabove-ar", "above")]), "gap"]
    """
    glyphs: list[Glyph] = []
    x = 0.0
    for item in spec:
        if item == "gap":
            x += WORD_SPACE / 1000.0 * size
            continue
        name, marks = item
        base = Glyph(name, x, baseline, size)
        glyphs.append(base)
        for mark in marks:
            mark_name, side = mark[0], mark[1]
            opts = mark[2] if len(mark) > 2 else {}
            glyphs.append(attach(glyphs, font, base, mark_name, side, **opts))
        x += font.advance(name) / 1000.0 * size
    return glyphs


def fit(spec, baseline: float, font: ArabicFont, max_size: float,
        measure: float) -> list[Glyph]:
    """Lay a word out at ``max_size``, shrinking it only if it overruns ``measure``."""
    glyphs = lay_out(spec, max_size, baseline, font)
    x0, x1 = ink_extent(glyphs, font)
    if x1 - x0 > measure:
        glyphs = lay_out(spec, max_size * measure / (x1 - x0), baseline, font)
    centre(glyphs, font)
    return glyphs
