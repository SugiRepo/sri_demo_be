"""
Modul Public API v1 — endpoint yang ditujukan untuk konsumen eksternal
(sistem instansi lain, vendor integrasi, mobile client).

Struktur:
    envelope.py    — model response standar { status, data, meta } / { status, error, meta }
    errors.py      — kode error standar + exception class kustom
    middleware.py  — audit log middleware (KAK §1.5.3.b jejak aktivitas)
    arsip.py       — endpoint domain Arsip (GET, POST, search, metadata)
    router.py      — agregator router v1
"""
