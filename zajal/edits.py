"""The corrections marked in yellow pen on ``artwork/zajal-labels-markup.pdf``.

One function per label. Each docstring records the reading of the pen marks;
``tools/inspect_markup.py`` prints the measurements they were derived from.
"""

from __future__ import annotations

from .document import LatinLine, Page
from .fonts import ArabicFont
from .layout import attach, fit

MEASURE = 310.0  # the width every wordmark in the family is set to


def _latin(page: Page, text: str, *, fallback: bool = False) -> None:
    """Reset the romanised name, keeping the original point size and tracking."""
    old = page.latin
    page.latin_changed = True
    tracking = old.size * 0.08 if fallback else old.tracking
    page.latin = LatinLine(text=text, x=old.x, y=old.y, size=old.size,
                           tracking=tracking, fallback=fallback)


def page01(page: Page, font: ArabicFont) -> None:
    """مشرقي ← مَشْرِقي — fatha on the meem, sukun on the sheen, kasra under the reh."""
    page.glyphs += [
        attach(page.glyphs, font, page.find("meem-ar.init"), "fatha-ar", "above"),
        attach(page.glyphs, font, page.find("seen-ar.medi.kash"), "sukun-ar", "above"),
        attach(page.glyphs, font, page.find("reh-ar.fina.kash"), "kasra-ar", "below"),
    ]


def page02(page: Page, font: ArabicFont) -> None:
    """عويسي ← عويسِي — kasra under the seen of the seen/alef-maksura ligature.

    The ligature draws both ســ and ـى, so the mark is nudged right of the
    ligature's centre to sit under the seen itself.
    """
    base = page.find("seen_alefMaksura-ar.fina.liga")
    page.glyphs.append(attach(page.glyphs, font, base, "kasra-ar", "below",
                              gap=-14.0, dx=36.0))


def page03(page: Page, font: ArabicFont) -> None:
    """فَلِكَىْ ← فَلَكَي — drop the sukun and the kasra, put a fatha on the lam."""
    page.remove(page.find("sukun-ar"))
    page.remove(page.find("kasra-ar"))
    page.glyphs.append(attach(page.glyphs, font,
                              page.find("lam-ar.medi.kash.001"), "fatha-ar", "above"))


def page04(page: Page, font: ArabicFont) -> None:
    """عِشْقٌ ← عِشْق — drop the tanween on the qaf."""
    page.remove(page.find("dammatan-ar"))


def page05(page: Page, font: ArabicFont) -> None:
    """لِقَاءٌ ← لِقَاء — drop the tanween on the hamza."""
    page.remove(page.find("dammatan-ar"))


def page06(page: Page, font: ArabicFont) -> None:
    """تَجَلَّيْ ← تَجَلّي — drop the fatha above the shadda and the sukun on the ya."""
    page.remove(page.find("fatha-ar", x=216.75))
    page.remove(page.find("sukun-ar"))


def page07(page: Page, font: ArabicFont) -> None:
    """دِفَاءٌ ← دِفْء / DAFAA ← DEFA.

    The alef and the tanween are struck out and the fatha on the feh becomes a
    sukun. The letters are laid out again so the hamza still joins the word.
    """
    baseline, size = page.glyphs[0].y, page.glyphs[0].size
    page.glyphs = fit(
        [
            ("hamza-ar", []),
            ("kashida-ar.kash3", []),
            ("fehDotless-ar.init.kash", [("dotabove-ar", "above"),
                                         ("sukun-ar", "above")]),
            ("dal-ar", [("kasra-ar", "below")]),
        ],
        baseline, font, max_size=size, measure=MEASURE)
    _latin(page, "DEFA")


def page08(page: Page, font: ArabicFont) -> None:
    """مهرجا ← مِهْرَجا / MAHRAJA ← MEHRAJA.

    The fatha on the jeem is set the way the designer set the one on page 6:
    left of the letter's centre and clear of its tall head.
    """
    page.glyphs += [
        attach(page.glyphs, font, page.find("meem-ar.init"), "kasra-ar", "below"),
        attach(page.glyphs, font, page.find("heh-ar.medi"), "sukun-ar", "above"),
        attach(page.glyphs, font, page.find("hah-ar.init.kash"), "fatha-ar", "above",
               gap=17.5, dx=-15.0),
    ]
    _latin(page, "MEHRAJA")


def page09(page: Page, font: ArabicFont) -> None:
    """دَيْرَةٌ ← أبُوظَبي / DEIERA ← ABU DHABY — the whole name is replaced."""
    baseline, size = page.glyphs[0].y, page.glyphs[0].size
    page.glyphs = fit(
        [
            ("alefMaksura-ar.fina", [("twodotshorizontalbelow-ar", "below")]),
            ("behDotless-ar.medi", [("dotbelow-ar", "below")]),
            ("tah-ar.medi", [("dotabove-ar", "above"), ("fatha-ar", "above")]),
            ("waw-ar.fina.kash", []),
            ("behDotless-ar.init.kash", [("dotbelow-ar", "below"),
                                         ("damma-ar", "above")]),
            ("alef-ar", [("hamza-ar", "above",
                          {"size": 0.36, "gap": 6.0, "dx": 10.0})]),
        ],
        baseline, font, max_size=size, measure=MEASURE)
    _latin(page, "ABU DHABY", fallback=True)


def page10(page: Page, font: ArabicFont) -> None:
    """رَحَّالٌ ← رَحَّال — drop the tanween on the lam."""
    page.remove(page.find("dammatan-ar"))


def page11(page: Page, font: ArabicFont) -> None:
    """إِنْطِلاَقٌ ← انْطِلاَق — drop the tanween on the qaf and the kasra under the alef."""
    page.remove(page.find("dammatan-ar"))
    page.remove(page.find("kasra-ar", x=435.04))


def page12(page: Page, font: ArabicFont) -> None:
    """فَارِسٌ ← فَارِس الظل / FARES ← FARES AL ZEL.

    The second word makes the line too long for the family's measure, so the
    decorative kashida inside فارس is dropped and the whole line is fitted.
    """
    baseline, size = page.glyphs[0].y, page.glyphs[0].size
    page.glyphs = fit(
        [
            ("lam-ar", []),
            ("tah-ar.medi", [("dotabove-ar", "above")]),
            ("lam-ar.init", []),
            ("alef-ar", []),
            "gap",
            ("seen-ar", []),
            ("reh-ar", [("kasra-ar", "below")]),
            ("alef-ar.fina.kash", []),
            ("fehDotless-ar.init.kash", [("dotabove-ar", "above"),
                                         ("fatha-ar", "above")]),
        ],
        baseline, font, max_size=size, measure=MEASURE)
    _latin(page, "FARES AL ZEL", fallback=True)


PAGES = [page01, page02, page03, page04, page05, page06,
         page07, page08, page09, page10, page11, page12]

# Glyphs the corrections need that the original subset never encoded.
EXTRA_GLYPHS = ["behDotless-ar.medi", "damma-ar"]
