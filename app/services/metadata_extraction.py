"""
Layer 1 Metadata Extraction — Rule-based regex.

Sasaran: ekstrak ~80% field standar dari naskah dinas Bahasa Indonesia
dengan latency < 5 ms dan zero ML dependency. Field yang tidak tertangkap
di sini di-fallback ke Layer 2 (NER mini-model) bila tersedia.

Field yang diekstrak:
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

Catatan: angka confidence bersifat heuristik untuk mendukung Layer 4
validasi (flag manual review bila confidence < threshold).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

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
    """Bundle hasil ekstraksi seluruh field."""

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


class ExtractionResult(BaseModel):
    """Top-level response: metadata + ringkasan & sumber teks."""

    metadata: ExtractedMetadata
    fields_filled: int
    fields_total: int
    overall_confidence: float
    extractor: str = "regex/v1"
    text_length: int


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
# Public entry point
# ------------------------------------------------------------------------------


def extract_metadata(text: str) -> ExtractionResult:
    """Ekstrak seluruh field metadata dari teks naskah dinas."""
    metadata = ExtractedMetadata()

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

    all_fields = list(metadata.model_dump().values())
    fields_filled = sum(1 for f in all_fields if f.get("found"))
    fields_total = len(all_fields)
    overall_confidence = (
        sum(f.get("confidence", 0.0) for f in all_fields) / fields_total
        if fields_total
        else 0.0
    )

    return ExtractionResult(
        metadata=metadata,
        fields_filled=fields_filled,
        fields_total=fields_total,
        overall_confidence=overall_confidence,
        text_length=len(text),
    )
