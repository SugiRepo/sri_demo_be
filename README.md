# sri-demo

FastAPI service for PDF/document upload, validation, Elasticsearch indexing, and search.

## Prerequisites

- Python 3.11+ (3.13 tested)
- PostgreSQL
- [Apache Tika](https://tika.apache.org/) server with OCR support (`apache/tika:latest-full`)
- Elasticsearch (local or Elastic Cloud)

## Quick start

```powershell
git clone <your-repo-url>
cd sri-demo

python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
# Edit .env with your DATABASE_URL, ELASTICSEARCH_URL, ELASTICSEARCH_API_KEY, etc.

python -m uvicorn main:app --reload
```

API docs: http://127.0.0.1:8000/docs

Or use the dev script:

```powershell
.\run-dev.ps1
```

## Environment variables

See [.env.example](.env.example). Required for full functionality:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `ELASTICSEARCH_URL` | Elasticsearch cluster URL |
| `ELASTICSEARCH_API_KEY` | API key (Elastic Cloud); leave empty for local ES without auth |
| `TIKA_ENDPOINT` | Tika server URL (e.g. `http://localhost:9998/tika`) |
| `TIKA_PDF_OCR_ENABLED` | `true` to OCR scanned PDFs (Tika full image + Tesseract) |
| `TIKA_OCR_LANGUAGE` | Tesseract languages, e.g. `eng+ind` for English + Indonesian |
| `TIKA_OCR_MAX_FILE_SIZE` | Max bytes per file for OCR (default 50MB) |
| `API_AUTH_ENABLED` | `true` to require `X-API-Key` on protected routes; `false` for local dev |
| `API_KEYS` | Comma-separated valid API keys (register generated keys manually) |

## API key authentication

Protected routes require header `X-API-Key: <your-key>` when `API_AUTH_ENABLED=true`.

Public (no key): `GET /health`, `GET /healthElasticsearch`.

**Bootstrap the first key** (does not update `.env` automatically):

```powershell
python -c "from app.services.api_key_generate import generate_api_key; print(generate_api_key())"
```

Copy the output into `.env` as `API_KEYS=sk_...`, restart uvicorn.

**Additional keys for partners** (requires an existing valid key):

```powershell
curl -X POST http://127.0.0.1:8000/api-keys/generate -H "X-API-Key: YOUR_EXISTING_KEY"
```

Response envelope (same as `/api/v1/*`):

```json
{
  "status": "success",
  "data": { "api_key": "sk_..." },
  "meta": { "request_id": "...", "timestamp": "...", "api_version": "1.0.0", "execution_time_ms": 0.85 }
}
```

Append the returned `data.api_key` to `API_KEYS` in `.env` (comma-separated), then restart.

**3rd-party example:**

```powershell
curl -H "X-API-Key: sk_your_key" "http://127.0.0.1:8000/documents/search?q=test"
```

Set `API_AUTH_ENABLED=false` to disable validation during local development.

## Main endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (public) |
| POST | `/api-keys/generate` | Generate new API key string (`SuccessResponse` envelope; register `data.api_key` in `.env`) |
| POST | `/upload` | Upload document (pypdf text check unless OCR enabled) |
| GET | `/documents/{document_id}` | Document status from PostgreSQL |
| GET | `/documents/download/{document_id}` | Download archived file when `status=indexed` |
| GET | `/documents/search?q=...` | Search Elasticsearch (`"phrase"` vs flexible unquoted) |
| POST | `/generate/pdf-image` | Build image-only PDF for OCR/upload testing (JSON body; success = PDF download, errors = `ApiError`) |
| POST | `/watermark-document/stamp` | Queue PDF watermark job (`SuccessResponse`, 202) |
| GET | `/watermark-documents` | List jobs (`SuccessResponse`; `?watermark_id=`, `?file_name=`) |
| GET | `/watermark-documents/{watermark_id}` | Job detail (`SuccessResponse`) |
| GET | `/watermark-documents/{watermark_id}/download` | Download PDF file (raw bytes; errors use `ApiError` envelope) |

JSON endpoints use `{ "status": "success", "data": {...}, "meta": {...} }`. Errors use `{ "status": "error", "error": { "code", "message", ... }, "meta": {...} }`.

**Watermark flow** (stored under `DOCUMENT_STORAGE_ROOT/watermarks/{year}/{date}/`):

```powershell
# 1. Submit job
curl -X POST http://127.0.0.1:8000/watermark-document/stamp `
  -H "X-API-Key: YOUR_KEY" `
  -F "file=@document.pdf" `
  -F "watermark=CONFIDENTIAL" `
  -F "create_by=myuser"

# 2. Check status
curl -H "X-API-Key: YOUR_KEY" http://127.0.0.1:8000/watermark-documents/{watermark_id}

# 3. Download when status is success
curl -H "X-API-Key: YOUR_KEY" `
  http://127.0.0.1:8000/watermark-documents/{watermark_id}/download `
  -o watermarked.pdf
```

Status values: `processing`, `success`, `failed`. Optional form fields: `filename`, `opacity`, `angle`, `create_by` (default `api`).

## External services

**Tika (with OCR)** — use the **full** image locally and in production:

```bash
docker run -p 9998:9998 apache/tika:latest-full
```

Enable OCR in `.env`:

```env
TIKA_PDF_OCR_ENABLED=true
TIKA_OCR_LANGUAGE=eng+ind
```

With OCR on, scanned (image-only) PDFs are allowed at upload; Tika extracts text in the background.

**PostgreSQL** — create database:

```sql
CREATE DATABASE sri_demo;
```

Tables are created on API startup (`init_db` in lifespan).

## Project layout

```
app/
  routers/       # HTTP routes
  services/      # PDF ingest, search, validation, storage
  models/        # SQLModel tables
  config.py      # Settings from .env
main.py          # FastAPI entry
```

## Notes

- Do not commit `.env` — it is gitignored.
- Uploaded files are stored under `storage/` (gitignored).
- Logs go to `logs/` (gitignored).
