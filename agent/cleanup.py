"""Limpieza post-ciclo (§14.2 paso 10 de v1-spec.md).

Responsabilidades:
1. Limpiar tmp/ (crops, PDFs descargados) — preservar heartbeat.lock/ y .gitkeep
2. Purgar entradas > 30 dias de state/processed-emails.json
"""

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config_schema import get_project_root


def clean_tmp() -> int:
    """Limpia archivos temporales en tmp/.

    Preserva:
    - tmp/heartbeat.lock/ (se maneja por separado en preflight.py)
    - tmp/.gitkeep

    Returns:
        Cantidad de items eliminados.
    """
    root = get_project_root()
    tmp_dir = root / "tmp"
    removed = 0

    if not tmp_dir.exists():
        return 0

    for item in tmp_dir.iterdir():
        # Preservar lock y .gitkeep
        if item.name in ("heartbeat.lock", ".gitkeep"):
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)
        removed += 1

    return removed


def purge_processed_emails(retention_days: int = 30) -> int:
    """Purga entradas antiguas de state/processed-emails.json (§13.1).

    Args:
        retention_days: Dias de retencion. Entradas mas antiguas se eliminan.

    Returns:
        Cantidad de entradas eliminadas.
    """
    root = get_project_root()
    state_path = root / "state" / "processed-emails.json"

    if not state_path.exists():
        return 0

    with open(state_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    processed = data.get("processed", [])
    if not processed:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    original_count = len(processed)

    kept = []
    for entry in processed:
        processed_at_str = entry.get("processed_at", "")
        try:
            processed_at = datetime.fromisoformat(processed_at_str)
            # Asegurar timezone-aware para comparacion
            if processed_at.tzinfo is None:
                processed_at = processed_at.replace(tzinfo=timezone.utc)
            if processed_at >= cutoff:
                kept.append(entry)
        except (ValueError, TypeError):
            # Entrada con timestamp invalido — conservar por seguridad
            kept.append(entry)

    purged = original_count - len(kept)

    if purged > 0:
        data["processed"] = kept
        # Escritura atomica: write-to-temp + rename
        tmp_path = state_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp_path.replace(state_path)

    return purged


def run_cleanup() -> dict:
    """Ejecuta todas las tareas de limpieza post-ciclo.

    Returns:
        Dict con resumen: {"tmp_removed": int, "emails_purged": int}
    """
    tmp_removed = clean_tmp()
    emails_purged = purge_processed_emails()

    return {
        "tmp_removed": tmp_removed,
        "emails_purged": emails_purged,
    }
