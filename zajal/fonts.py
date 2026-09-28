"""Metrics for the fonts embedded in the label artwork.

Both text fonts in the source PDF are subsets with a private encoding, so the
only reliable source of truth for codes, widths and outlines is the PDF itself.
Everything here is read back out of the document rather than hard-coded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

import pymupdf
from fontTools.cffLib import CFFFontSet
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

ARABIC_RES = "Tc3"  # Guesswhat-Exceptional
LATIN_RES = "TT5"  # Plantagenet Cherokee

_DIFFERENCES = re.compile(r"/Differences\s*\[(.*?)\]", re.S)
_NAME = re.compile(r"/([^\s/\[\]]+)|(\d+)")
_WIDTHS = re.compile(r"/Widths\s*\[(.*?)\]", re.S)
_FIRSTCHAR = re.compile(r"/FirstChar\s+(\d+)")
_BFRANGE = re.compile(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>")


@dataclass(frozen=True)
class Box:
    """Glyph ink box in font units (y up from the baseline)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2


class ArabicFont:
    """The Guesswhat-Exceptional CFF subset used for the Arabic wordmarks."""

    def __init__(self, doc: pymupdf.Document, xref: int):
        self.doc = doc
        self.xref = xref
        obj = doc.xref_object(xref)

        first = int(_FIRSTCHAR.search(obj).group(1))
        names = [m.group(1) for m in _NAME.finditer(_DIFFERENCES.search(obj).group(1))
                 if m.group(1)]
        self.code_to_name = {first + i: n for i, n in enumerate(names)}
        self.name_to_code = {n: c for c, n in self.code_to_name.items()}

        widths = [float(v) for v in _WIDTHS.search(obj).group(1).split()]
        self.width = {self.code_to_name[first + i]: w for i, w in enumerate(widths)}

        _, _, _, buf = doc.extract_font(xref)
        cff = CFFFontSet()
        cff.decompile(BytesIO(buf), None)
        charstrings = cff[cff.fontNames[0]].CharStrings
        self.box: dict[str, Box] = {}
        for name in charstrings.keys():
            pen = BoundsPen(charstrings)
            charstrings[name].draw(pen)
            self.box[name] = Box(*(pen.bounds or (0, 0, 0, 0)))
        self.outline_names = set(self.box)

    def advance(self, name: str) -> float:
        """Advance width in font units; unencoded glyphs fall back to their ink box."""
        if name in self.width:
            return self.width[name]
        box = self.box[name]
        return 0.0 if box.width == 0 else box.x1 + 20.0

    def is_mark(self, name: str) -> bool:
        return self.advance(name) == 0.0

    def ensure_encoded(self, names) -> None:
        """Add glyphs that exist in the CFF but are missing from /Differences."""
        missing = [n for n in names if n not in self.name_to_code]
        if not missing:
            return
        for name in missing:
            if name not in self.outline_names:
                raise KeyError(f"glyph {name!r} is not in the embedded font subset")
            code = max(self.code_to_name) + 1
            self.code_to_name[code] = name
            self.name_to_code[name] = code
            self.width[name] = self.advance(name)

        obj = self.doc.xref_object(self.xref)
        first = int(_FIRSTCHAR.search(obj).group(1))
        last = max(self.code_to_name)
        order = [self.code_to_name[c] for c in range(first, last + 1)]
        diff = " ".join(["33"] + [f"/{n}" for n in order])
        widths = " ".join(f"{self.width[n]:g}" for n in order)
        self.doc.xref_set_key(self.xref, "Encoding",
                              f"<</Type/Encoding/Differences[{diff}]>>")
        self.doc.xref_set_key(self.xref, "LastChar", str(last))
        self.doc.xref_set_key(self.xref, "Widths", f"[{widths}]")


class LatinFont:
    """The Plantagenet Cherokee TrueType subset used for the romanised names."""

    def __init__(self, doc: pymupdf.Document, xref: int):
        obj = doc.xref_object(xref)
        first = int(_FIRSTCHAR.search(obj).group(1))
        widths = [float(v) for v in _WIDTHS.search(obj).group(1).split()]

        tounicode = int(re.search(r"/ToUnicode\s+(\d+)", obj).group(1))
        cmap = doc.xref_stream(tounicode).decode("latin-1")
        self.char_to_code = {}
        for lo, _hi, uni in _BFRANGE.findall(cmap):
            self.char_to_code[chr(int(uni, 16))] = int(lo, 16)
        self.code_to_char = {c: ch for ch, c in self.char_to_code.items()}
        self.width = {self.code_to_char[first + i]: w
                      for i, w in enumerate(widths) if first + i in self.code_to_char}

        _, _, _, buf = doc.extract_font(xref)
        self.units_per_em = TTFont(BytesIO(buf))["head"].unitsPerEm

    def supports(self, text: str) -> bool:
        return all(ch == " " or ch in self.char_to_code for ch in text)

    def encode(self, text: str) -> str:
        return "".join(chr(self.char_to_code[ch]) for ch in text)

    def text_width(self, text: str, size: float) -> float:
        return sum(self.width[ch] for ch in text) / 1000.0 * size


class FallbackLatinFont:
    """Stand-in serif for letters the embedded Plantagenet subset does not carry."""

    def __init__(self, path: str):
        self.path = path
        self.font = pymupdf.Font(fontfile=path)

    def supports(self, text: str) -> bool:
        return True

    def text_width(self, text: str, size: float) -> float:
        return self.font.text_length(text, fontsize=size)
