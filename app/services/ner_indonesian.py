"""
Layer 2 Metadata Extraction — Indonesian Named Entity Recognition (NER).

Wrapper tipis di atas spaCy + model `id_ner_spacy_indonesian` (~50 MB disk,
~400 MB RAM, ~20 ms inference per halaman). Singleton loader supaya model
hanya dimuat 1x per proses worker uvicorn.

Design goals:
- **Lazy load**: model tidak dimuat saat import; hanya saat pertama dipanggil.
  Bila spaCy / model belum ter-install, service tetap importable (degrade
  ke `is_available() == False`) — Layer 1 regex tetap jalan.
- **Stateless API**: semua fungsi pure, terima `text`, kembalikan `list[NerEntity]`.
- **Stable contract**: label entitas tidak di-translate; konsumen
  (Layer combinator) yang memutuskan mapping ke field naskah dinas.

Catatan akurasi:
Model ini dilatih di korpus berita umum, bukan naskah dinas pemerintah.
Untuk demo PoC ini cukup; iterasi berikutnya disarankan fine-tune di
korpus terlabel ANRI (lihat KAK_GAP_ANALYSIS.md §1.2 bis).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("app.services.ner_indonesian")

# Identitas model di logs/extractor signature. Naikkan versi bila ganti model.
NER_MODEL_NAME = "id_ner_spacy_indonesian"
NER_EXTRACTOR_VERSION = "ner/spacy-id-asmud-v1.1"


class NerEntity(BaseModel):
    """Satu entitas yang dideteksi NER (raw output, sebelum mapping ke field)."""

    label: str = Field(..., description="Label entitas mentah dari model (mis. PER, ORG, GPE, LAW).")
    text: str = Field(..., description="Teks entitas seperti yang muncul di dokumen.")
    start: int = Field(..., description="Offset karakter awal di teks sumber.")
    end: int = Field(..., description="Offset karakter akhir (exclusive).")


class _NerSingleton:
    """
    Thread-safe lazy loader.

    Pertama kali `get()` dipanggil:
        - import spacy + load model (~2 detik di Apple Silicon).
        - subsequent calls langsung pakai instance yang sudah dimuat.
    """

    def __init__(self) -> None:
        self._nlp = None
        self._load_error: Optional[str] = None
        self._lock = threading.Lock()
        self._load_time_ms: float = 0.0

    def get(self):
        if self._nlp is not None:
            return self._nlp
        if self._load_error is not None:
            return None
        with self._lock:
            if self._nlp is not None:
                return self._nlp
            if self._load_error is not None:
                return None
            self._load()
            return self._nlp

    def _load(self) -> None:
        t0 = time.perf_counter()
        try:
            import spacy  # type: ignore
        except ImportError as exc:
            self._load_error = (
                "spaCy belum ter-install. Jalankan: pip install spacy"
            )
            logger.warning("NER tidak tersedia: %s (%s)", self._load_error, exc)
            return
        try:
            self._nlp = spacy.load(NER_MODEL_NAME)
        except Exception as exc:  # OSError, ImportError, dll.
            self._load_error = (
                f"Model '{NER_MODEL_NAME}' tidak ter-install. "
                "Jalankan: pip install "
                "https://huggingface.co/asmud/ner-spacy-indonesian/resolve/main/"
                "id_ner_spacy_indonesian-1.1.0-py3-none-any.whl"
            )
            logger.warning("NER tidak tersedia: %s (%s)", self._load_error, exc)
            return
        self._load_time_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "NER model loaded: %s (%.0f ms, %d entity labels)",
            NER_MODEL_NAME,
            self._load_time_ms,
            len(self._nlp.get_pipe("ner").labels),
        )

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    @property
    def load_time_ms(self) -> float:
        return self._load_time_ms


_singleton = _NerSingleton()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_available() -> bool:
    """True bila model bisa dipakai. Memicu load on first call."""
    return _singleton.get() is not None


def availability_reason() -> Optional[str]:
    """Pesan diagnosis bila NER tidak tersedia (None bila OK)."""
    _singleton.get()  # trigger load
    return _singleton.load_error


def warmup() -> bool:
    """
    Paksa load model sekarang (mis. saat startup uvicorn).
    Return True bila berhasil. Tidak melempar exception.
    """
    available = is_available()
    if available:
        logger.info("NER warmup OK (load_time=%.0f ms)", _singleton.load_time_ms)
    else:
        logger.warning("NER warmup gagal: %s", _singleton.load_error)
    return available


def extract_entities(text: str) -> list[NerEntity]:
    """
    Jalankan NER pada `text`. Kembalikan list kosong bila NER tidak tersedia
    atau teks kosong.

    Kompleksitas: O(n) di panjang teks; ~20 ms per halaman A4 di CPU.
    """
    if not text or not text.strip():
        return []
    nlp = _singleton.get()
    if nlp is None:
        return []

    doc = nlp(text)
    return [
        NerEntity(
            label=ent.label_,
            text=ent.text.strip(),
            start=ent.start_char,
            end=ent.end_char,
        )
        for ent in doc.ents
        if ent.text.strip()  # filter whitespace-only
    ]
