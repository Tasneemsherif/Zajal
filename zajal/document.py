"""Read the label pages into an editable model and write them back out.

The artwork is machine-generated PDF: every Arabic glyph is painted by its own
``q … cm BT … Tm /Tc3 1 Tf (code) Tj ET Q`` block and the romanised name by a
single ``/TT5`` block. That makes it practical to decode a page into a glyph
list, edit the list, and regenerate the drawing operators from scratch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pymupdf

from .fonts import ARABIC_RES, ArabicFont, LatinFont

PAGE_CENTRE = 306.0  # every element in the artwork is centred on the page axis
NAME_COLOUR = "0 0.035 0.102 0 k"

_ARABIC_BLOCK = re.compile(
    r"q\s+([\d.]+)\s+0\s+0\s+([\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\n?cm\s*"
    r"BT\s+([\d.]+)\s+0\s+0\s+([\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\n?"
    r"Tm\s*/" + ARABIC_RES + r"\s+1\s+Tf\s*\((.*?)\)\s*Tj\s*ET\s*Q",
    re.S,
)
_LATIN_BLOCK = re.compile(
    r"q\s+([\d.]+)\s+0\s+0\s+([\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\n?cm\s*"
    r"BT\s+([\d.]+)\s+Tc\s+([\d.]+)\s+0\s+0\s+([\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\n?"
    r"Tm\s*/TT5\s+1\s+Tf\s*(\[.*?\]\s*TJ|\(.*?\)\s*Tj)\s*ET\s*Q",
    re.S,
)
_IMAGE_BLOCK = re.compile(
    r"q\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+re\s+W\s+n\s*\n?/\w+\s*\n?ri\s+q\s+"
    r"[^Q]*?/Im\d+\s+Do\s+Q\s+Q",
    re.S,
)
_STRING = re.compile(r"\((.*?)(?<!\\)\)", re.S)

_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f",
            "(": "(", ")": ")", "\\": "\\"}


def unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt in _ESCAPES:
                out.append(_ESCAPES[nxt])
                i += 2
                continue
            if nxt in "01234567":
                digits = ""
                j = i + 1
                while j < len(s) and len(digits) < 3 and s[j] in "01234567":
                    digits += s[j]
                    j += 1
                out.append(chr(int(digits, 8)))
                i = j
                continue
            out.append(nxt)
            i += 2
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def escape(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


@dataclass
class Glyph:
    """One Arabic glyph painted at an absolute position on the page."""

    name: str
    x: float
    y: float  # baseline, PDF coordinates (y up)
    size: float

    def ink(self, font: ArabicFont) -> tuple[float, float, float, float]:
        """Ink box as (x0, top, x1, bottom) in top-left page coordinates."""
        box = font.box[self.name]
        s = self.size / 1000.0
        return (self.x + box.x0 * s, 792 - (self.y + box.y1 * s),
                self.x + box.x1 * s, 792 - (self.y + box.y0 * s))


@dataclass
class LatinLine:
    text: str
    x: float
    y: float
    size: float
    tracking: float  # extra advance per glyph, in points
    fallback: bool = False  # set in a substitute serif, drawn outside the stream

    def width(self, font) -> float:
        return font.text_width(self.text, self.size) + self.tracking * max(len(self.text) - 1, 0)


@dataclass
class Page:
    index: int
    glyphs: list[Glyph]
    latin: LatinLine | None
    extra_latin: list[LatinLine] = field(default_factory=list)
    latin_changed: bool = False
    _stream: str = ""
    _latin_raw: str = ""
    _cuts: list[tuple[int, int]] = field(default_factory=list)

    def find(self, name: str, x: float | None = None, tol: float = 1.0) -> Glyph:
        matches = [g for g in self.glyphs if g.name == name
                   and (x is None or abs(g.x - x) <= tol)]
        if len(matches) != 1:
            where = "" if x is None else f" near x={x}"
            raise LookupError(
                f"page {self.index + 1}: expected exactly one {name}{where}, "
                f"found {len(matches)}")
        return matches[0]

    def remove(self, glyph: Glyph) -> None:
        self.glyphs.remove(glyph)


def read_page(doc: pymupdf.Document, index: int, latin_font: LatinFont) -> Page:
    stream = doc[index].read_contents().decode("latin-1")
    glyphs: list[Glyph] = []
    cuts: list[tuple[int, int]] = []
    arabic_font = _arabic_font(doc)

    for m in _ARABIC_BLOCK.finditer(stream):
        sx, sy, ex, ey, fs, _fy, tx, ty, codes = m.groups()
        sx, sy, ex, ey = float(sx), float(sy), float(ex), float(ey)
        x = sx * float(tx) + ex
        y = sy * float(ty) + ey
        size = sx * float(fs)
        for ch in unescape(codes):
            name = arabic_font.code_to_name[ord(ch)]
            glyphs.append(Glyph(name, x, y, size))
            x += arabic_font.advance(name) / 1000.0 * size
        cuts.append(m.span())

    latin = None
    latin_raw = ""
    for m in _LATIN_BLOCK.finditer(stream):
        sx, sy, ex, ey, tc, fs, _fy, tx, ty, payload = m.groups()
        sx, ex, ey = float(sx), float(ex), float(ey)
        text = "".join(latin_font.code_to_char[ord(c)]
                       for part in _STRING.findall(payload)
                       for c in unescape(part))
        size = sx * float(fs)
        latin = LatinLine(text=text, x=sx * float(tx) + ex, y=sx * float(ty) + ey,
                          size=size, tracking=float(tc) * size)
        latin_raw = m.group(0)
        cuts.append(m.span())

    for m in _IMAGE_BLOCK.finditer(stream):
        cuts.append(m.span())

    return Page(index=index, glyphs=glyphs, latin=latin, _stream=stream,
                _latin_raw=latin_raw if latin else "", _cuts=sorted(cuts))


_ARABIC_FONT: ArabicFont | None = None


def _arabic_font(doc: pymupdf.Document) -> ArabicFont:
    global _ARABIC_FONT
    if _ARABIC_FONT is None:
        xref = next(f[0] for f in doc[0].get_fonts(full=True)
                    if "Guesswhat" in f[3])
        _ARABIC_FONT = ArabicFont(doc, xref)
    return _ARABIC_FONT


def render_page(page: Page, arabic_font: ArabicFont, latin_font: LatinFont) -> bytes:
    """Rebuild the page content stream with the edited text."""
    keep, cursor = [], 0
    for start, end in page._cuts:
        keep.append(page._stream[cursor:start])
        cursor = end
    keep.append(page._stream[cursor:])
    body = "".join(keep)

    out = [body, f"\nq {NAME_COLOUR}\n"]
    for g in sorted(page.glyphs, key=lambda g: (g.size, g.x)):
        code = arabic_font.name_to_code[g.name]
        out.append(f"BT 0 Tc /{ARABIC_RES} {g.size:.4f} Tf "
                   f"1 0 0 1 {g.x:.4f} {g.y:.4f} Tm ({escape(chr(code))}) Tj ET\n")

    if page.latin and not page.latin.fallback:
        if page.latin_changed:
            payload = escape(latin_font.encode(page.latin.text))
            line = page.latin
            out.append(f"BT {line.tracking:.4f} Tc /TT5 {line.size:.4f} Tf "
                       f"1 0 0 1 {line.x:.4f} {line.y:.4f} Tm ({payload}) Tj ET\n")
        else:
            out.append(page._latin_raw)
    for line in page.extra_latin:
        if line.fallback:
            continue
        payload = escape(latin_font.encode(line.text))
        out.append(f"BT {line.tracking:.4f} Tc /TT5 {line.size:.4f} Tf "
                   f"1 0 0 1 {line.x:.4f} {line.y:.4f} Tm ({payload}) Tj ET\n")

    out.append("\nQ\n")
    return "".join(out).encode("latin-1")
