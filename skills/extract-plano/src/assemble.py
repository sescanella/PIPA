"""
Assembler: merges per-region JSON files into a validated SpoolRecord.

Usage (from PIPA root):
    python -m skills.extract-plano.src.assemble tmp/crops/MK-1342-MO-13012-001_0
    python -m skills.extract-plano.src.assemble tmp/crops/   # all subdirectories

Usage (from skills/extract-plano/):
    python -m src.assemble ../../tmp/crops/MK-1342-MO-13012-001_0
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .paths import find_pipa_root
from .schemas import (
    CajetinData,
    CorteRow,
    MaterialRow,
    SoldaduraRow,
    SpoolRecord,
)


def load_json(path: Path) -> list | dict:
    """Load a JSON file, returning empty list/dict if missing or corrupted."""
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"  WARNING: Corrupted JSON in {path.name}: {e}")
        return []


def _parse_rows(model, raw: list | dict, region: str, errors: list[str]) -> list:
    """Parse a list of raw dicts into Pydantic models, skipping invalid rows."""
    if not isinstance(raw, list):
        return []
    parsed = []
    for i, row in enumerate(raw):
        try:
            parsed.append(model(**row))
        except ValidationError as e:
            msg = f"{region} row {i}: {e}"
            print(f"  WARNING: Skipping invalid {msg}")
            errors.append(msg)
    return parsed


def assemble(crops_dir: Path, output_dir: Path | None = None) -> SpoolRecord:
    """
    Read per-region JSON files from a crops directory and
    assemble into a validated SpoolRecord.

    Args:
        crops_dir: Directory containing materiales.json, soldaduras.json, etc.
        output_dir: Where to save the final JSON. Defaults to tmp/json/.

    Returns:
        Validated SpoolRecord.
    """
    crops_dir = Path(crops_dir)
    stem = crops_dir.name

    if output_dir is None:
        pipa_root = find_pipa_root()
        output_dir = pipa_root / "tmp" / "json"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load region JSONs
    materiales_raw = load_json(crops_dir / "materiales.json")
    soldaduras_raw = load_json(crops_dir / "soldaduras.json")
    cortes_raw = load_json(crops_dir / "cortes.json")
    cajetin_raw = load_json(crops_dir / "cajetin.json")

    errors: list[str] = []

    # Parse rows with per-row error handling
    materiales = _parse_rows(MaterialRow, materiales_raw, "materiales", errors)
    soldaduras = _parse_rows(SoldaduraRow, soldaduras_raw, "soldaduras", errors)
    cortes = _parse_rows(CorteRow, cortes_raw, "cortes", errors)

    try:
        cajetin = CajetinData(**cajetin_raw) if isinstance(cajetin_raw, dict) else CajetinData()
    except ValidationError as e:
        errors.append(f"cajetin: {e}")
        cajetin = CajetinData()

    status = "partial" if errors else "ok"

    record = SpoolRecord(
        pdf_name=f"{stem}.pdf",
        status=status,
        errors=errors,
        cajetin=cajetin,
        materiales=materiales,
        soldaduras=soldaduras,
        cortes=cortes,
    )

    # Save validated JSON
    out_path = output_dir / f"{stem}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(record.model_dump_json(indent=2, by_alias=True))

    print(f"Saved: {out_path}")
    print(f"  Materiales: {len(record.materiales)} rows")
    print(f"  Soldaduras: {len(record.soldaduras)} rows")
    print(f"  Cortes: {len(record.cortes)} rows")
    print(f"  OT: {record.cajetin.ot or 'N/A'}")
    print(f"  OF: {record.cajetin.of_ or 'N/A'}")

    return record


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m src.assemble <crops-dir>")
        print("  python -m src.assemble tmp/crops/           # all subdirs")
        sys.exit(1)

    target = Path(sys.argv[1])

    if not target.exists():
        print(f"Error: {target} not found")
        sys.exit(1)

    # Check if target is a specific crops subdirectory or a parent
    if (target / "materiales.json").exists() or (target / "cajetin.json").exists():
        # It's a specific crops directory
        assemble(target)
    elif target.is_dir():
        # It's the parent crops/ directory — process all subdirs
        subdirs = sorted(d for d in target.iterdir() if d.is_dir())
        if not subdirs:
            print(f"No subdirectories in {target}")
            sys.exit(1)
        print(f"Assembling {len(subdirs)} records...\n")
        for subdir in subdirs:
            try:
                assemble(subdir)
            except Exception as e:
                print(f"  ERROR [{subdir.name}]: {e}")
            print()
        print("Done.")
    else:
        print(f"Error: {target} is not a directory")
        sys.exit(1)


if __name__ == "__main__":
    main()
