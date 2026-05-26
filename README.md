# sri-demo

FastAPI service for PDF/document upload, validation, Elasticsearch indexing, and search.

## Prerequisites

- Python 3.11+ (3.13 tested)
- PostgreSQL
- [Apache Tika](https://tika.apache.org/) server (default `http://localhost:9998`)
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

## Main endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/upload` | Upload document (PDF validated early; others skip pypdf check) |
| GET | `/documents/{document_id}` | Document status from PostgreSQL |
| GET | `/documents/search?q=...` | Search Elasticsearch (`"phrase"` vs flexible unquoted) |

## External services

**Tika** — run separately (Docker example):

```bash
docker run -p 9998:9998 apache/tika:latest
```

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
