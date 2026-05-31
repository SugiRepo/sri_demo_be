import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api_v1.middleware import install_v1_middleware
from app.api_v1.router import api_v1_router
from app.database import init_db
from app.logging_config import setup_logging
from app.routers import documents, health, metadata


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    yield


# OpenAPI customization — terlihat di /docs (Swagger UI) dan /openapi.json.
API_DESCRIPTION = """
**Public API SRIKANDI Search & Archive Service** — PoC interoperabilitas
sesuai KAK §1.5.3 (API interoperabilitas, skema metadata, error checking, jejak
aktivitas) dan §2.9 (Mesin Pencarian Berkecepatan Tinggi).

## Konvensi

Semua endpoint di bawah `/api/v1/*` mengembalikan response envelope yang
seragam:

- **Sukses:** `{ "status": "success", "data": <T>, "meta": {...} }`
- **Gagal:**  `{ "status": "error",   "error": {...},  "meta": {...} }`

Setiap response menyertakan header:

- `X-Request-ID` — UUID korelasi antar sistem (boleh juga dikirim oleh klien
  agar request id konsisten end-to-end).
- `X-Response-Time-Ms` — latensi server (tanpa network).

## Error handling

Daftar lengkap kode error stabil tersedia di `GET /api/v1/errors`. Konsumen
eksternal dianjurkan membuat logic switch berdasarkan `error.code`, bukan
berdasarkan pesan (yang dapat berubah / diterjemahkan).

## Jejak aktivitas

Setiap call ke `/api/v1/*` dicatat di audit log (file `logs/audit.log`,
format JSON-Lines). Entri terbaru dapat diambil via `GET /api/v1/audit-log`.

## Versi

Versi mayor di-pin pada path (`/api/v1`). Perubahan breaking akan dirilis
sebagai `/api/v2` agar konsumen lama tidak putus.
""".strip()

OPENAPI_TAGS_METADATA = [
    {
        "name": "Sistem",
        "description": "Informasi versi, katalog error, dan audit log.",
    },
    {
        "name": "Arsip (Naskah Dinas)",
        "description": (
            "Operasi domain arsip naskah dinas: detail, pencarian full-text, "
            "upload, dan ekstraksi metadata."
        ),
    },
    {
        "name": "Health",
        "description": "Endpoint legacy health-check (non-versioned).",
    },
    {
        "name": "Documents",
        "description": "Endpoint legacy (non-versioned). Tetap dipertahankan untuk kompatibilitas internal.",
    },
    {
        "name": "Metadata Extraction",
        "description": "Endpoint legacy ekstraksi metadata.",
    },
]

app = FastAPI(
    title="SRIKANDI Search & Archive Service",
    summary="API arsip & pencarian naskah dinas — PoC ANRI 2026",
    description=API_DESCRIPTION,
    version="1.0.0",
    contact={
        "name": "Tim Pengembang SRIKANDI",
        "url": "https://www.anri.go.id",
    },
    license_info={
        "name": "Apache-2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0",
    },
    openapi_tags=OPENAPI_TAGS_METADATA,
    lifespan=lifespan,
)

_cors_origins_env = os.getenv(
    "CORS_ALLOW_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)
allow_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
)

# Pasang middleware & exception handler v1.
install_v1_middleware(app)

# Public API v1 (endpoint untuk konsumen eksternal).
app.include_router(api_v1_router)

# Endpoint legacy non-versioned — tetap dipertahankan agar tidak memutus klien lama.
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(metadata.router)
