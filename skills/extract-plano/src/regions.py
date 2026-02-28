"""
Region definitions for technical drawing PDF cropping.

Each region is defined as percentage-based coordinates relative to
page dimensions (all PDFs are 1190.52 x 842.04 points).
"""

from dataclasses import dataclass

import fitz  # PyMuPDF


@dataclass(frozen=True)
class Region:
    """A rectangular crop region defined as percentages of page dimensions."""
    name: str
    left_pct: float
    top_pct: float
    right_pct: float
    bottom_pct: float
    zoom: float

    def to_rect(self, page_width: float, page_height: float):
        """Convert percentage-based region to a fitz.Rect (left, top, right, bottom)."""
        return fitz.Rect(
            page_width * self.left_pct,
            page_height * self.top_pct,
            page_width * self.right_pct,
            page_height * self.bottom_pct,
        )


# ── Region definitions ──────────────────────────────────────────────
# Coordinates validated against 1190.52 x 842.04 pt pages.

MATERIALES = Region(
    name="materiales",
    left_pct=0.64,
    top_pct=0.0,
    right_pct=1.0,
    bottom_pct=0.30,
    zoom=2.5,
)

SOLDADURAS = Region(
    name="soldaduras",
    left_pct=0.60,
    top_pct=0.28,
    right_pct=1.0,
    bottom_pct=0.52,
    zoom=2.5,
)

CORTES = Region(
    name="cortes",
    left_pct=0.55,
    top_pct=0.52,
    right_pct=1.0,
    bottom_pct=0.72,
    zoom=2.5,
)

CAJETIN = Region(
    name="cajetin",
    left_pct=0.0,
    top_pct=0.70,
    right_pct=1.0,
    bottom_pct=1.0,
    zoom=3.0,
)

# All regions in processing order
ALL_REGIONS = [MATERIALES, SOLDADURAS, CORTES, CAJETIN]
