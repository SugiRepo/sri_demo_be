"""
Hybrid Metadata Extraction — Layer 1 (regex) + Layer 2 (NER).

Sasaran: ekstrak ~80% field standar dari naskah dinas Bahasa Indonesia
dengan latency < 50 ms dan minimum dependency.

Layer 1 — Rule-based regex (selalu jalan):
- nomor_surat            : Nomor surat (mis. "B-1234/SETJEN/UM.01.04/V/2026")
- sifat                  : Biasa / Penting / Rahasia / Segera / Sangat Rahasia
- lampiran               : Jumlah/keterangan lampiran
- perihal                : Perihal / hal surat
- tempat                 : Tempat penandatanganan (mis. "Jakarta")
- tanggal                : Tanggal dalam format ISO (YYYY-MM-DD)
- tanggal_raw            : Tanggal dalam format sumber (mis. "28 Mei 2026")
- penerima               : Tujuan surat (setelah "Yth.")
- klasifikasi_code       : Kode klasifikasi dari nomor surat (mis. "UM.01.04")
- nip                    : NIP penandatangan (18 digit, sesuai PP 11/2017)

Layer 2 — Named Entity Recognition (opsional, `use_ner=True`):
- instansi_pengirim      : ORG paling awal di header (institusi pengirim)
- organisasi_disebut     : ORG lain yang muncul di body
- lokasi_disebut         : GPE (kota / propinsi / negara) yang disebut
- fasilitas_disebut      : FAC (bangunan, bandara, stadion, dsb.)
- regulasi_disebut       : LAW (UU, PP, Permen, dsb.)

Catatan: angka confidence bersifat heuristik untuk mendukung Layer 4
validasi (flag manual review bila confidence < threshold).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.services import ner_indonesian
from app.services.ner_indonesian import (
    NER_EXTRACTOR_VERSION,
    NerEntity,
)

MONTHS_ID: dict[str, int] = {
    "januari": 1,
    "februari": 2,
    "maret": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "agustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "desember": 12,
}

# Bulan dalam Bahasa Inggris — sering muncul di korpus dummy / system-generated.
MONTHS_EN: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

MONTHS: dict[str, int] = {**MONTHS_ID, **MONTHS_EN}

_MONTHS_REGEX_PART = "|".join(MONTHS.keys())

SIFAT_VALUES: set[str] = {
    "biasa",
    "penting",
    "rahasia",
    "sangat rahasia",
    "segera",
}

# ------------------------------------------------------------------------------
# Compiled regex patterns
# ------------------------------------------------------------------------------

# "Nomor       : B-1234/SETJEN/UM.01.04/V/2026"  atau  "Nomor : 0005/UM/2024"
_NOMOR_PATTERN = re.compile(
    r"(?im)^\s*nomor\s*:\s*([^\n\r]+?)\s*(?:\s{2,}|$)"
)

_SIFAT_PATTERN = re.compile(
    r"(?im)^\s*sifat\s*:\s*([A-Za-z ]+?)\s*(?:\s{2,}|$)"
)

_LAMPIRAN_PATTERN = re.compile(
    r"(?im)^\s*lampiran\s*:\s*([^\n\r]+?)\s*(?:\s{2,}|$)"
)

# Perihal mungkin multi-line; tangkap minimal baris pertama.
_PERIHAL_PATTERN = re.compile(
    r"(?im)^\s*perihal\s*:\s*([^\n\r]+?)\s*$"
)

# "Jakarta, 28 Mei 2026" / "Jakarta 28 Mei 2026"
_TEMPAT_TANGGAL_PATTERN = re.compile(
    r"(?i)\b([A-Z][A-Za-z .'-]{2,40}?),?\s+"
    r"(\d{1,2})\s+"
    + r"(" + _MONTHS_REGEX_PART + r")\s+"
    r"(\d{4})\b"
)

# Field tanggal eksplisit: "Tanggal     : 12 August 2024" / "Tanggal: 28 Mei 2026"
_TANGGAL_LABEL_PATTERN = re.compile(
    r"(?im)^\s*tanggal\s*:\s*"
    r"(\d{1,2})\s+"
    + r"(" + _MONTHS_REGEX_PART + r")\s+"
    r"(\d{4})\s*$"
)

# Field klasifikasi eksplisit: "Klasifikasi : UM - Umum" / "Klasifikasi: UM.01.04"
_KLASIFIKASI_LABEL_PATTERN = re.compile(
    r"(?im)^\s*klasifikasi\s*:\s*([A-Z]{2}(?:\.\d{2}(?:\.\d{2})?)?)"
    r"(?:\s*[-–]\s*([A-Za-z ]+))?\s*$"
)

# Tujuan setelah "Yth.", "Kepada Yth.", atau "Kepada Yth :".
# Capture lines sampai blank line (whitespace-only line) atau "Dengan hormat".
_YTH_PATTERN = re.compile(
    r"(?is)(?:kepada\s+)?yth\.?\s*[:\n]?\s*"
    r"((?:[^\n]+\n?)+?)"
    r"(?=\n\s*\n|\n\s*dengan\s+hormat|\n\s*assalam|$)"
)

# NIP. 19650512 199003 1 002  atau  NIP. 196505121990031002
_NIP_PATTERN = re.compile(
    r"(?i)\bNIP\.?\s*[:.]?\s*((?:\d[\s]?){18,25})"
)

# Ekstrak kode klasifikasi dari nomor surat: UM, UM.01, UM.01.04
_KLASIFIKASI_FROM_NOMOR_PATTERN = re.compile(
    r"/([A-Z]{2}(?:\.\d{2}(?:\.\d{2})?)?)/"
)


# ------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------


class ExtractedField(BaseModel):
    """Hasil ekstraksi satu field, lengkap dengan confidence & raw match."""

    value: Optional[str] = None
    found: bool = False
    confidence: float = 0.0
    raw_match: Optional[str] = None


class ExtractedMetadata(BaseModel):
    """Bundle hasil ekstraksi seluruh field (Layer 1 + Layer 2)."""

    # --- Layer 1 (regex) — selalu populated ---
    nomor_surat: ExtractedField = Field(default_factory=ExtractedField)
    sifat: ExtractedField = Field(default_factory=ExtractedField)
    lampiran: ExtractedField = Field(default_factory=ExtractedField)
    perihal: ExtractedField = Field(default_factory=ExtractedField)
    tempat: ExtractedField = Field(default_factory=ExtractedField)
    tanggal: ExtractedField = Field(default_factory=ExtractedField)
    tanggal_raw: ExtractedField = Field(default_factory=ExtractedField)
    penerima: ExtractedField = Field(default_factory=ExtractedField)
    klasifikasi_code: ExtractedField = Field(default_factory=ExtractedField)
    nip: ExtractedField = Field(default_factory=ExtractedField)

    # --- Layer 2 (NER) — populated hanya bila use_ner=True ---
    instansi_pengirim: ExtractedField = Field(
        default_factory=ExtractedField,
        description="Instansi pengirim (deteksi NER ORG paling awal di header).",
    )
    organisasi_disebut: list[str] = Field(
        default_factory=list,
        description="ORG lain yang muncul di body (selain pengirim).",
    )
    lokasi_disebut: list[str] = Field(
        default_factory=list,
        description="GPE (kota / propinsi / negara) yang disebut.",
    )
    fasilitas_disebut: list[str] = Field(
        default_factory=list,
        description="FAC (bangunan, bandara, infrastruktur) yang disebut.",
    )
    regulasi_disebut: list[str] = Field(
        default_factory=list,
        description="LAW (UU, PP, Permen, peraturan) yang disebut.",
    )


# Field Layer 1 yang dihitung untuk metrik fields_filled / overall_confidence.
# Field Layer 2 (list[str]) tidak ikut karena bersifat suplemen, bukan core.
_LAYER1_FIELD_NAMES = (
    "nomor_surat",
    "sifat",
    "lampiran",
    "perihal",
    "tempat",
    "tanggal",
    "tanggal_raw",
    "penerima",
    "klasifikasi_code",
    "nip",
)


class ExtractionResult(BaseModel):
    """Top-level response: metadata + ringkasan & sumber teks."""

    metadata: ExtractedMetadata
    fields_filled: int = Field(
        ..., description="Jumlah field Layer 1 yang berhasil di-ekstrak."
    )
    fields_total: int = Field(
        ..., description="Total field Layer 1 yang dievaluasi (selalu 10)."
    )
    overall_confidence: float
    extractor: str = Field(
        default="regex/v1",
        description=(
            "Signature ekstraktor. 'regex/v1' bila Layer 1 saja, "
            "'regex/v1+ner/spacy-id-asmud-v1.1' bila hybrid."
        ),
    )
    text_length: int

    # --- Layer 2 telemetry (default: tidak aktif) ---
    ner_used: bool = Field(
        default=False, description="True bila Layer 2 NER ikut dijalankan."
    )
    ner_available: bool = Field(
        default=True,
        description=(
            "False bila NER diminta tapi model tidak ter-install / gagal load. "
            "Layer 1 tetap berjalan."
        ),
    )
    ner_processing_time_ms: float = Field(
        default=0.0, description="Waktu inference NER (0 bila NER tidak dipakai)."
    )
    ner_entities: list[NerEntity] = Field(
        default_factory=list,
        description=(
            "Raw NER entities (untuk transparansi & debugging). "
            "Mapping ke field naskah dinas ada di `metadata.*_disebut` & "
            "`metadata.instansi_pengirim`."
        ),
    )


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------


def _clean(text: str) -> str:
    """Rapikan whitespace berlebih dan trailing punctuation ringan."""
    return re.sub(r"[ \t]+", " ", text).strip().strip(",;")


# ------------------------------------------------------------------------------
# Field extractors (pure functions)
# ------------------------------------------------------------------------------


def extract_nomor(text: str) -> ExtractedField:
    match = _NOMOR_PATTERN.search(text)
    if not match:
        return ExtractedField()
    value = _clean(match.group(1))
    if not value or value == "-":
        return ExtractedField()
    confidence = 0.95 if "/" in value else 0.70
    return ExtractedField(
        value=value,
        found=True,
        confidence=confidence,
        raw_match=match.group(0).strip(),
    )


def extract_sifat(text: str) -> ExtractedField:
    match = _SIFAT_PATTERN.search(text)
    if not match:
        return ExtractedField()
    value = _clean(match.group(1)).lower()
    if not value:
        return ExtractedField()
    is_known = value in SIFAT_VALUES
    return ExtractedField(
        value=value.title(),
        found=True,
        confidence=0.98 if is_known else 0.60,
        raw_match=match.group(0).strip(),
    )


def extract_lampiran(text: str) -> ExtractedField:
    match = _LAMPIRAN_PATTERN.search(text)
    if not match:
        return ExtractedField()
    value = _clean(match.group(1))
    if not value:
        return ExtractedField()
    return ExtractedField(
        value=value,
        found=True,
        confidence=0.95,
        raw_match=match.group(0).strip(),
    )


def extract_perihal(text: str) -> ExtractedField:
    match = _PERIHAL_PATTERN.search(text)
    if not match:
        return ExtractedField()
    value = _clean(match.group(1))
    if not value:
        return ExtractedField()
    return ExtractedField(
        value=value,
        found=True,
        confidence=0.92,
        raw_match=match.group(0).strip(),
    )


def _build_tanggal_fields(
    day: int,
    month: int,
    year: int,
    month_label: str,
    raw_match: str,
    confidence: float,
) -> tuple[ExtractedField, ExtractedField]:
    """Bangun (tanggal_iso, tanggal_raw) dari komponen tanggal yang sudah ter-parse."""
    iso = datetime(year, month, day).date().isoformat()
    return (
        ExtractedField(
            value=iso,
            found=True,
            confidence=confidence,
            raw_match=raw_match,
        ),
        ExtractedField(
            value=f"{day} {month_label.capitalize()} {year}",
            found=True,
            confidence=confidence,
            raw_match=raw_match,
        ),
    )


def _parse_tempat_tanggal(
    text: str,
) -> tuple[ExtractedField, ExtractedField, ExtractedField]:
    """
    Hasil: (tempat, tanggal_iso, tanggal_raw).

    Strategi:
    1. Coba field eksplisit "Tanggal : 12 August 2024" — biasanya tidak ada tempat.
    2. Coba pattern "Jakarta, 28 Mei 2026" — tempat + tanggal di satu kalimat.
    """
    label_match = _TANGGAL_LABEL_PATTERN.search(text)
    if label_match:
        try:
            day = int(label_match.group(1))
            month_name = label_match.group(2).lower()
            month = MONTHS[month_name]
            year = int(label_match.group(3))
            raw = label_match.group(0).strip()
            tanggal, tanggal_raw = _build_tanggal_fields(
                day, month, year, month_name, raw, confidence=0.98
            )
            return ExtractedField(), tanggal, tanggal_raw
        except (ValueError, KeyError):
            pass

    for match in _TEMPAT_TANGGAL_PATTERN.finditer(text):
        tempat_raw = _clean(match.group(1))
        # Heuristik: nama tempat ≤ 4 kata, bukan keyword di tengah body.
        if len(tempat_raw.split()) > 4:
            continue
        if tempat_raw.lower() in {"tanggal", "hari", "tahun", "bulan", "pada"}:
            continue
        try:
            day = int(match.group(2))
            month_name = match.group(3).lower()
            month = MONTHS[month_name]
            year = int(match.group(4))
        except (ValueError, KeyError):
            continue
        raw = match.group(0).strip()
        tanggal, tanggal_raw = _build_tanggal_fields(
            day, month, year, month_name, raw, confidence=0.95
        )
        return (
            ExtractedField(
                value=tempat_raw,
                found=True,
                confidence=0.85,
                raw_match=raw,
            ),
            tanggal,
            tanggal_raw,
        )
    return ExtractedField(), ExtractedField(), ExtractedField()


_PENERIMA_NOISE_PREFIXES = (
    "dengan hormat",
    "assalamu",
    "salam sejahtera",
    "salam hormat",
    "sehubungan dengan",
    "bersama ini",
    "menindaklanjuti",
    "berdasarkan",
    "merujuk pada",
)


def _is_penerima_noise(line: str) -> bool:
    """Filter baris yang bukan tujuan surat — biasanya pembuka paragraf body."""
    normalized = line.lower().strip()
    if normalized in {"di", "di-", "di tempat", "di-tempat", "ditempat"}:
        return True
    return any(normalized.startswith(p) for p in _PENERIMA_NOISE_PREFIXES)


def extract_penerima(text: str) -> ExtractedField:
    match = _YTH_PATTERN.search(text)
    if not match:
        return ExtractedField()
    lines: list[str] = []
    for raw_line in match.group(1).split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if _is_penerima_noise(line):
            break
        lines.append(line)
    if not lines:
        return ExtractedField()
    value = " · ".join(lines[:3])
    return ExtractedField(
        value=value,
        found=True,
        confidence=0.80,
        raw_match=match.group(0).strip(),
    )


def extract_klasifikasi(text: str, nomor: Optional[str]) -> ExtractedField:
    """
    Strategi: field eksplisit "Klasifikasi : UM - Umum" > parsing dari nomor.
    Field eksplisit lebih dipercaya karena bisa menyertakan deskripsi lengkap.
    """
    label_match = _KLASIFIKASI_LABEL_PATTERN.search(text)
    if label_match:
        code = label_match.group(1)
        description = label_match.group(2)
        value = f"{code} - {description.strip()}" if description else code
        return ExtractedField(
            value=value,
            found=True,
            confidence=0.97,
            raw_match=label_match.group(0).strip(),
        )

    if not nomor:
        return ExtractedField()
    match = _KLASIFIKASI_FROM_NOMOR_PATTERN.search(nomor)
    if not match:
        return ExtractedField()
    return ExtractedField(
        value=match.group(1),
        found=True,
        confidence=0.85,
        raw_match=match.group(0),
    )


def extract_nip(text: str) -> ExtractedField:
    match = _NIP_PATTERN.search(text)
    if not match:
        return ExtractedField()
    raw = match.group(1)
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ExtractedField()
    is_valid_length = len(digits) == 18
    return ExtractedField(
        value=digits,
        found=True,
        confidence=0.98 if is_valid_length else 0.60,
        raw_match=match.group(0).strip(),
    )


# ------------------------------------------------------------------------------
# Layer 2 — NER classification ke field naskah dinas
# ------------------------------------------------------------------------------

# Heuristik header: ORG pertama dalam N karakter pertama dianggap pengirim.
# Naskah dinas biasanya punya kop surat 1-3 baris di paling atas.
_HEADER_CHAR_LIMIT = 400

# Label form / keyword surat yang sering ke-tag salah oleh NER model
# (model dilatih di korpus berita, bukan naskah dinas pemerintah).
_NOISE_KEYWORDS = {
    "sifat",
    "nomor",
    "lampiran",
    "perihal",
    "tanggal",
    "yth",
    "kepada yth",
    "dengan hormat",
    "tembusan",
    "hormat kami",
}

# Indikator kuat suatu string adalah organisasi sungguhan
# (institusi pemerintah / korporasi). Bila string ORG tidak memuat salah
# satu ini DAN < 3 kata, kemungkinan besar false positive.
_ORG_INDICATORS = {
    "kementerian",
    "lembaga",
    "direktorat",
    "badan",
    "biro",
    "dinas",
    "kantor",
    "sekretariat",
    "inspektorat",
    "pusat",
    "balai",
    "unit",
    "fakultas",
    "universitas",
    "institut",
    "akademi",
    "sekolah",
    "rumah sakit",
    "yayasan",
    "perusahaan",
    "perseroan",
    "koperasi",
    "asosiasi",
    "ikatan",
    "majelis",
    "komisi",
    "komite",
    "dewan",
    "kpu",
    "kpk",
    "bpk",
    "bpkp",
    "bin",
    "tni",
    "polri",
    "anri",
    "lan",
    "bkn",
    "bappenas",
    "bappeda",
    "bumn",
    "bumd",
    "pt ",  # "PT Angkasa..."
    "cv ",  # "CV Sumber..."
    "ud ",
    "pdam",
    "pln",
    "pertamina",
}

# Indikator kuat suatu string adalah dokumen regulasi.
# Sangat ketat: tanpa indikator ini, NER label LAW di-skip.
_REGULASI_INDICATORS = (
    "undang-undang",
    "undang undang",
    "peraturan pemerintah",
    "peraturan presiden",
    "peraturan menteri",
    "peraturan daerah",
    "peraturan kepala",
    "keputusan presiden",
    "keputusan menteri",
    "keputusan kepala",
    "instruksi presiden",
    "perpres ",
    "permen ",
    "perda ",
    "perka ",
    "kepres ",
    "kepmen ",
    "inpres ",
    "uu nomor",
    "uu no.",
    "pp nomor",
    "pp no.",
)


def _normalize(text: str) -> str:
    """Lower-case + collapse whitespace + strip trailing punctuation."""
    cleaned = re.sub(r"\s+", " ", text).strip().lower()
    return cleaned.rstrip(":,.")


def _is_noise_entity(text: str) -> bool:
    """Filter universal: terlalu pendek, hanya whitespace, atau keyword form."""
    normalized = _normalize(text)
    if not normalized or len(normalized) < 4:
        return True
    if normalized in _NOISE_KEYWORDS:
        return True
    return False


def _is_valid_org(text: str) -> bool:
    """
    Heuristik: ORG diterima bila salah satu kondisi:
    1. Mengandung indikator institusional (Kementerian, PT, Lembaga, dst.) — accept.
    2. Punya minimal 2 token alfabet yang masing-masing ≥ 4 karakter
       (mis. "Universitas Indonesia"). Filter false-positive seperti
       "KU - Keuangan" (hanya 1 token panjang).
    """
    normalized = _normalize(text)
    if any(ind in normalized for ind in _ORG_INDICATORS):
        return True
    long_alpha_tokens = [
        t for t in re.split(r"\W+", normalized) if t.isalpha() and len(t) >= 4
    ]
    return len(long_alpha_tokens) >= 2


def _is_valid_location(text: str) -> bool:
    """
    Heuristik: lokasi diterima bila bukan akronim singkat & bukan gelar.
    Tolak: ALL-CAPS singkat (≤ 4 char, "API", "USA"), strings dengan banyak titik
    ("S.E.", "M.Sc.", "Ph.D."), atau angka.
    """
    cleaned = text.strip()
    if any(ch.isdigit() for ch in cleaned):
        return False
    # Gelar academic biasanya punya 2+ titik di tengah token pendek.
    if cleaned.count(".") >= 2 and len(cleaned) <= 6:
        return False
    # Akronim ALL-CAPS singkat — terlalu ambigu untuk lokasi.
    if cleaned.isupper() and len(cleaned) <= 4:
        return False
    return True


def _is_valid_regulasi(text: str) -> bool:
    """Hanya terima string yang mengandung indikator regulasi eksplisit."""
    normalized = _normalize(text)
    return any(ind in normalized for ind in _REGULASI_INDICATORS)


def _is_valid_facility(text: str) -> bool:
    """Filter dasar untuk FAC: tidak terlalu pendek dan bukan keyword form."""
    cleaned = text.strip()
    return len(cleaned) >= 5


def _dedup_preserve_order(items: list[str]) -> list[str]:
    """Hapus duplikat case-insensitive, pertahankan urutan kemunculan pertama."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = _normalize(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def _classify_entities(
    entities: list[NerEntity],
    metadata: ExtractedMetadata,
) -> None:
    """
    Map NER entities → field naskah dinas (mutasi `metadata` in-place).

    Aturan klasifikasi (dengan noise filtering domain-specific):
    - **instansi_pengirim**: ORG valid pertama di header (offset < 400).
    - **organisasi_disebut**: ORG valid lain, dedup.
    - **lokasi_disebut**: GPE valid (bukan gelar / akronim), dedup.
    - **fasilitas_disebut**: FAC valid, dedup.
    - **regulasi_disebut**: LAW yang mengandung indikator regulasi eksplisit, dedup.
    """
    instansi_pengirim_set = False
    org_others: list[str] = []
    locations: list[str] = []
    facilities: list[str] = []
    regulations: list[str] = []

    for ent in entities:
        if _is_noise_entity(ent.text):
            continue
        label = ent.label.upper()
        text = ent.text.strip()

        if label == "ORG":
            if not _is_valid_org(text):
                continue
            if not instansi_pengirim_set and ent.start < _HEADER_CHAR_LIMIT:
                metadata.instansi_pengirim = ExtractedField(
                    value=text,
                    found=True,
                    confidence=0.80,
                    raw_match=text,
                )
                instansi_pengirim_set = True
            else:
                org_others.append(text)
        elif label == "GPE":
            if _is_valid_location(text):
                locations.append(text)
        elif label == "FAC":
            if _is_valid_facility(text):
                facilities.append(text)
        elif label == "LAW":
            if _is_valid_regulasi(text):
                regulations.append(text)

    metadata.organisasi_disebut = _dedup_preserve_order(org_others)
    metadata.lokasi_disebut = _dedup_preserve_order(locations)
    metadata.fasilitas_disebut = _dedup_preserve_order(facilities)
    metadata.regulasi_disebut = _dedup_preserve_order(regulations)


# ------------------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------------------


def extract_metadata(text: str, use_ner: bool = False) -> ExtractionResult:
    """
    Ekstrak metadata dari teks naskah dinas.

    Args:
        text: Teks halaman pertama naskah dinas.
        use_ner: Bila True, jalankan juga Layer 2 (NER) untuk mengisi
            field free-form (instansi pengirim, lokasi, organisasi, dst.).
            Default False supaya backward compatible dengan caller lama.

    Layer 1 selalu jalan. Layer 2 dijalankan opsional dan tidak menggagalkan
    response bila model NER tidak tersedia — hanya `ner_available=False`
    yang di-flag di response.
    """
    import time as _time

    metadata = ExtractedMetadata()

    # --- Layer 1 (regex) ---
    metadata.nomor_surat = extract_nomor(text)
    metadata.sifat = extract_sifat(text)
    metadata.lampiran = extract_lampiran(text)
    metadata.perihal = extract_perihal(text)

    tempat, tanggal, tanggal_raw = _parse_tempat_tanggal(text)
    metadata.tempat = tempat
    metadata.tanggal = tanggal
    metadata.tanggal_raw = tanggal_raw

    metadata.penerima = extract_penerima(text)
    metadata.klasifikasi_code = extract_klasifikasi(text, metadata.nomor_surat.value)
    metadata.nip = extract_nip(text)

    # --- Metrik Layer 1 ---
    layer1_values = [
        getattr(metadata, name).model_dump() for name in _LAYER1_FIELD_NAMES
    ]
    fields_filled = sum(1 for f in layer1_values if f.get("found"))
    fields_total = len(layer1_values)
    overall_confidence = (
        sum(f.get("confidence", 0.0) for f in layer1_values) / fields_total
        if fields_total
        else 0.0
    )

    # --- Layer 2 (NER, opsional) ---
    ner_entities: list[NerEntity] = []
    ner_used = False
    ner_available = True
    ner_processing_time_ms = 0.0
    extractor = "regex/v1"

    if use_ner:
        ner_available = ner_indonesian.is_available()
        if ner_available:
            ner_t0 = _time.perf_counter()
            ner_entities = ner_indonesian.extract_entities(text)
            ner_processing_time_ms = (_time.perf_counter() - ner_t0) * 1000
            _classify_entities(ner_entities, metadata)
            ner_used = True
            extractor = f"regex/v1+{NER_EXTRACTOR_VERSION}"

    return ExtractionResult(
        metadata=metadata,
        fields_filled=fields_filled,
        fields_total=fields_total,
        overall_confidence=overall_confidence,
        extractor=extractor,
        text_length=len(text),
        ner_used=ner_used,
        ner_available=ner_available,
        ner_processing_time_ms=round(ner_processing_time_ms, 2),
        ner_entities=ner_entities,
    )
