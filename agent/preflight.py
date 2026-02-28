"""Pre-flight checks antes de ejecutar un ciclo de heartbeat (§14.2 de v1-spec.md).

Checks:
1. Horario activo (07:00-22:00 America/Santiago)
2. Lock directory (tmp/heartbeat.lock) — adquirir o detectar stale
3. Conectividad a internet
"""

import json
import os
import platform
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from config_schema import PIPAConfig, get_project_root


@dataclass
class PreflightResult:
    passed: bool
    reason: Optional[str] = None  # None si paso; mensaje descriptivo si fallo
    error_type: Optional[str] = None  # Tipo para logs/consecutive_failures.json


def check_active_hours(config: PIPAConfig) -> PreflightResult:
    """Verifica si estamos dentro del horario activo (§14.2 paso 1)."""
    tz = ZoneInfo(config.agent.timezone)
    now = datetime.now(tz)
    current_time = now.time()

    start_parts = config.agent.active_hours.start.split(":")
    end_parts = config.agent.active_hours.end.split(":")
    start = time(int(start_parts[0]), int(start_parts[1]))
    end = time(int(end_parts[0]), int(end_parts[1]))

    if start <= current_time <= end:
        return PreflightResult(passed=True)
    return PreflightResult(
        passed=False,
        reason=f"Fuera de horario activo: {current_time.strftime('%H:%M')} "
               f"(activo {config.agent.active_hours.start}-{config.agent.active_hours.end})",
        error_type="preflight_failed",
    )


def _read_lock_info(lock_dir: Path) -> Optional[dict]:
    """Lee info.json del lock directory."""
    info_path = lock_dir / "info.json"
    if not info_path.exists():
        return None
    with open(info_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _is_pid_alive(pid: int) -> bool:
    """Verifica si un PID esta vivo. Compatible con Windows y Unix."""
    if platform.system() == "Windows":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    else:
        # Unix: os.kill con signal 0 verifica existencia sin matar
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def acquire_lock(config: PIPAConfig) -> PreflightResult:
    """Adquiere lock directory atomico (§14.3).

    Retorna PreflightResult.passed=True si se adquirio el lock.
    Si hay lock existente, aplica stale detection antes de fallar.
    """
    root = get_project_root()
    lock_dir = root / "tmp" / "heartbeat.lock"

    try:
        os.makedirs(lock_dir)
    except FileExistsError:
        # Lock existe — verificar si es stale
        info = _read_lock_info(lock_dir)
        if info is None:
            # Lock sin info.json — tratar como stale
            shutil.rmtree(lock_dir, ignore_errors=True)
            try:
                os.makedirs(lock_dir)
            except FileExistsError:
                return PreflightResult(
                    passed=False,
                    reason="Lock directory existe y no se pudo re-adquirir",
                    error_type="lock_active",
                )
        else:
            pid = info.get("pid")
            started_at_str = info.get("started_at", "")

            # Verificar si PID sigue vivo
            pid_alive = _is_pid_alive(pid) if pid else False

            if not pid_alive:
                # PID no existe — lock abandonado
                shutil.rmtree(lock_dir, ignore_errors=True)
                try:
                    os.makedirs(lock_dir)
                except FileExistsError:
                    return PreflightResult(
                        passed=False,
                        reason="Lock abandonado pero no se pudo re-adquirir",
                        error_type="lock_active",
                    )
            else:
                # PID existe — verificar timeout (25 min)
                try:
                    started_at = datetime.fromisoformat(started_at_str)
                    elapsed = (datetime.now(started_at.tzinfo) - started_at).total_seconds()
                    if elapsed > 25 * 60:
                        # Timeout — tratar como stale
                        shutil.rmtree(lock_dir, ignore_errors=True)
                        try:
                            os.makedirs(lock_dir)
                        except FileExistsError:
                            return PreflightResult(
                                passed=False,
                                reason="Lock con timeout pero no se pudo re-adquirir",
                                error_type="lock_active",
                            )
                    else:
                        # Ciclo en curso — no ejecutar
                        return PreflightResult(
                            passed=False,
                            reason=f"Otro ciclo en curso (PID {pid}, "
                                   f"inicio {started_at_str})",
                            error_type="lock_active",
                        )
                except (ValueError, TypeError):
                    # started_at invalido — tratar como stale
                    shutil.rmtree(lock_dir, ignore_errors=True)
                    try:
                        os.makedirs(lock_dir)
                    except FileExistsError:
                        return PreflightResult(
                            passed=False,
                            reason="Lock con timestamp invalido y no se pudo re-adquirir",
                            error_type="lock_active",
                        )

    # Lock adquirido — escribir info.json
    tz = ZoneInfo(config.agent.timezone)
    info = {
        "pid": os.getpid(),
        "started_at": datetime.now(tz).isoformat(),
    }
    info_path = lock_dir / "info.json"
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)

    return PreflightResult(passed=True)


def release_lock() -> None:
    """Libera el lock directory. Llamar en bloque finally."""
    root = get_project_root()
    lock_dir = root / "tmp" / "heartbeat.lock"
    shutil.rmtree(lock_dir, ignore_errors=True)


def check_internet() -> PreflightResult:
    """Verifica conectividad a internet (§14.2 paso 3)."""
    try:
        urllib.request.urlopen("https://www.google.com", timeout=10)
        return PreflightResult(passed=True)
    except Exception:
        return PreflightResult(
            passed=False,
            reason="Sin conectividad a internet",
            error_type="no_internet",
        )


def run_preflight(config: PIPAConfig) -> PreflightResult:
    """Ejecuta todos los pre-flight checks en orden.

    Orden: horario -> lock -> internet.
    Se detiene en el primer fallo.
    """
    # 1. Horario activo
    result = check_active_hours(config)
    if not result.passed:
        return result

    # 2. Lock directory
    result = acquire_lock(config)
    if not result.passed:
        return result

    # 3. Internet
    result = check_internet()
    if not result.passed:
        # Si falla internet, liberar el lock que acabamos de adquirir
        release_lock()
        return result

    return PreflightResult(passed=True)
