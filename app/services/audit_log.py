"""
Audit log service — KAK §1.5.3.b "catatan jejak aktivitas".

Setiap call ke /api/v1/* dicatat sebagai 1 baris JSON di logs/audit.log.
Format JSON-Lines memudahkan ingest ke ELK / Datadog / SIEM nantinya.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger("app.services.audit_log")

_LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_AUDIT_PATH = _LOG_DIR / "audit.log"

# Tulis dilindungi lock supaya tidak corrupt antar request konkuren.
_write_lock = threading.Lock()


def write_entry(entry: dict[str, Any]) -> None:
    """Tulis 1 entri audit ke file (JSON-Lines)."""
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **entry,
    }
    line = json.dumps(payload, ensure_ascii=False, default=str)
    try:
        with _write_lock, _AUDIT_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        # Audit log tidak boleh memblokir request; log error saja.
        logger.error("Gagal menulis audit log: %s", exc)


def read_recent(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """
    Ambil entri audit terbaru. Untuk PoC pakai pembacaan file
    sederhana — pada produksi sebaiknya pindah ke datastore terindeks.
    """
    if not _AUDIT_PATH.exists():
        return []

    # Baca dari belakang biar yang terbaru duluan, tanpa load seluruh file.
    entries: list[dict[str, Any]] = []
    try:
        with _AUDIT_PATH.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        logger.error("Gagal membaca audit log: %s", exc)
        return []

    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            entries.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
        if len(entries) >= offset + limit:
            break

    return entries[offset : offset + limit]


def total_count() -> int:
    """Jumlah total entri audit (dipakai untuk pagination meta)."""
    if not _AUDIT_PATH.exists():
        return 0
    try:
        with _AUDIT_PATH.open("r", encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
    except OSError:
        return 0


def iter_all() -> Iterator[dict[str, Any]]:
    """Iterator generator untuk seluruh entri (mis. untuk export)."""
    if not _AUDIT_PATH.exists():
        return
    with _AUDIT_PATH.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                continue
