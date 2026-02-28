"""
Multi-region cropping engine for technical drawing PDFs.

Extracts regions (materiales, soldaduras, cortes, cajetin) from a PDF
and saves each as a PNG image.

Usage (from PIPA root):
    python -m skills.extract-plano.src.crop tmp/archivo.pdf
    python -m skills.extract-plano.src.crop tmp/              # all PDFs in directory

Usage (from skills/extract-plano/):
    python -m src.crop ../../tmp/archivo.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz  # PyMuPDF

from .paths import find_pipa_root
from .regions import ALL_REGIONS, Region


def crop_region(page, region: Region, output_path: Path) -> dict:
    """Crop a single region from a PDF page and save as PNG."""
    rect = page.rect
    clip = region.to_rect(rect.width, rect.height)
    mat = fitz.Matrix(region.zoom, region.zoom)
    pix = page.get_pixmap(matrix=mat, clip=clip)
    pix.save(str(output_path))
    return {
        "region": region.name,
        "path": str(output_path),
        "width": pix.width,
        "height": pix.height,
    }


def crop_pdf(pdf_path: Path, output_dir: Path | None = None) -> list[dict]:
    """
    Crop all regions from a PDF and save PNGs.

    Args:
        pdf_path: Path to the input PDF.
        output_dir: Directory where crops/{stem}/ will be created.
                    Defaults to tmp/ relative to PIPA project root.

    Returns:
        List of dicts with region name, path, and dimensions.
    """
    pdf_path = Path(pdf_path)
    stem = pdf_path.stem

    if output_dir is None:
        # Default: PIPA_ROOT/tmp/crops/{stem}/
        pipa_root = find_pipa_root()
        output_dir = pipa_root / "tmp" / "crops" / stem
    else:
        output_dir = Path(output_dir) / stem

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        raise RuntimeError(f"Cannot open PDF '{pdf_path}': {e}") from e

    if len(doc) == 0:
        doc.close()
        raise ValueError(f"PDF '{pdf_path}' has no pages")

    page = doc[0]

    results = []
    for region in ALL_REGIONS:
        png_path = output_dir / f"{region.name}.png"
        info = crop_region(page, region, png_path)
        results.append(info)
        print(f"  {region.name}: {png_path.name} ({info['width']}x{info['height']}px)")

    doc.close()
    return results


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m src.crop <pdf-file>")
        print("  python -m src.crop <directory>")
        sys.exit(1)

    target = Path(sys.argv[1])

    if not target.exists():
        print(f"Error: {target} not found")
        sys.exit(1)

    if target.is_file() and target.suffix.lower() == ".pdf":
        pdf_files = [target]
    elif target.is_dir():
        pdf_files = sorted(target.glob("*.pdf"))
        if not pdf_files:
            print(f"No PDF files in {target}")
            sys.exit(1)
    else:
        print(f"Error: {target} is not a PDF file or directory")
        sys.exit(1)

    print(f"Processing {len(pdf_files)} PDF(s)...\n")

    for pdf_path in pdf_files:
        print(f"[{pdf_path.name}]")
        try:
            crop_pdf(pdf_path)
        except Exception as e:
            print(f"  ERROR: {e}")
        print()

    print("Done.")


if __name__ == "__main__":
    main()
