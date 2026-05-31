# Gap Analysis: KAK SRIKANDI 2026 (Addendum) vs Repo `sri_demo_be` (+ Frontend `sri_demo_fe`)

> **Revisi 3 — 31 Mei 2026.** Penambahan: PoC interoperabilitas (Public API v1) dan Layer 2 metadata extraction (NER Bahasa Indonesia hybrid). Audiens: panitia/evaluator teknis ANRI.

**Dokumen sumber**
- KAK: *KAK Pengembangan SRIKANDI Addendum Tahun 2026*, Direktorat TI Kearsipan, Arsip Nasional RI (29 halaman, Mei 2026), khususnya **§2.9 Proof of Concept**.
- Repo backend: `sri_demo_be` — FastAPI + Postgres + Tika + Elasticsearch Cloud untuk upload/indexing/search dokumen PDF.
- Repo frontend: `sri_demo_fe` — Vite + React 19 + React Router 7 + Tailwind 4 (SPA) untuk demonstrasi UX pencarian dan upload.

**Konteks**
Repo ini adalah PoC yang ditujukan untuk membuktikan kapabilitas teknis penyedia jasa sesuai **KAK §2.9 (Proof of Concept)**. PoC bukan aplikasi produksi — lingkupnya terbatas pada **pembuktian** beberapa kapabilitas teknis yang dievaluasi pada tahap Evaluasi Teknis tender. Fokus repo ini adalah sub-PoC **"Mesin Pencarian Berkecepatan Tinggi"**, dengan sentuhan pada sub-PoC **AI Metadata Extraction** dan **Async Processing**.

**Changelog**
- **2026-05-31 (Rev. 3)**
  - **Public API v1 untuk interoperabilitas** sub-PoC selesai. Versioned path `/api/v1/*`, response envelope seragam, 15 kode error stabil di `/api/v1/errors`, audit log JSON-Lines, header `X-Request-ID` + `X-Response-Time-Ms`, Swagger UI custom di `/docs`. File: `app/api_v1/`.
  - **Layer 2 metadata extraction (hybrid)** ditambahkan: NER Bahasa Indonesia via spaCy `id_ner_spacy_indonesian` (komunitas, 19 entity labels) + filter heuristik domain-specific. Aktif dengan `?use_ner=true`. Field tambahan: `instansi_pengirim`, `organisasi_disebut`, `lokasi_disebut`, `fasilitas_disebut`, `regulasi_disebut`. RAM +200 MB, latency +13–35 ms warm. Warm-up otomatis saat startup uvicorn (disable via `NER_WARMUP=0`). File: `app/services/ner_indonesian.py`, `app/services/metadata_extraction.py`.
  - Catatan: NER yang digunakan **bukan** IndoBERT fine-tuned. Interface stabil sehingga upgrade ke IndoBERT-Lite NER fine-tuned (lihat §1.2 *bis*) hanya butuh swap dalam 1 file tanpa breaking change.
- **2026-05-28 (Rev. 2)**
  - Bug B-01 (`collapse` di field `text`) — **selesai diperbaiki** via resolver dinamis `_resolve_collapse_field()` di `app/services/document_search.py`.
  - Bug B-03 (`python-multipart`) — **selesai** ditambahkan ke `requirements.txt`.
  - Elasticsearch dipindahkan dari Docker lokal ke **Elastic Cloud** (region `asia-southeast2.gcp`).
  - CORS middleware ditambahkan di `main.py` (allow `http://localhost:5173,3000`).
  - **Frontend `sri_demo_fe`** dibuat (Vite + React Router 7) sebagai bukti UX — lihat §1.5.
  - Script generator korpus & seeder ditambahkan (`scripts/generate_corpus.py`, `scripts/seed_corpus.py`); ~44 dokumen sudah ter-index.
  - Pengukuran latensi awal terdokumentasi di §1.1.bis.
- **2026-05-27 (Rev. 1)** — versi awal dokumen.

**Skala penilaian status**
- ✅ **Sudah ada** — fitur terbukti berfungsi end-to-end di repo.
- 🟡 **Sebagian** — fondasi ada tapi kurang aspek kunci yang diminta KAK.
- ❌ **Belum ada** — fitur tidak ada di repo, harus dibangun.
- ➖ **Di luar scope** — KAK menuntut tapi tidak relevan dengan PoC pencarian (komponen ini dibangun di lain repo/aplikasi besar SRIKANDI).

---

## 1. Pemetaan ke KAK §2.9 — Proof of Concept

KAK §2.9 berisi 9 sub-PoC. Repo `sri_demo_be` (+ companion `sri_demo_fe`) paling pas untuk sub-PoC **"Mesin Pencarian Berkecepatan Tinggi"** dan menyentuh **"AI Metadata Extraction"** serta **"Async Processing"**.

### 1.1 Mesin Pencarian Berkecepatan Tinggi *(target utama repo ini)*

| # | Requirement KAK §2.9 | Status | Catatan |
|---|---|---|---|
| a | Pencarian full-text menggunakan Mesin Pencarian | ✅ | **Elasticsearch Cloud 9.x** (region `asia-southeast2.gcp`) + Tika untuk ekstraksi konten PDF per halaman. Hasil di-collapse satu baris per dokumen (halaman skor tertinggi yang ditampilkan). Bukti: `GET /documents/search?q=pengelolaan` mengembalikan 3 dokumen, total 28 halaman cocok, dengan highlight `<em>` per snippet. |
| b | Response time < 100 ms | 🟡 | **Pengukuran awal warm: 92 ms** untuk kueri `pengelolaan` (lihat §1.1 *bis*). Belum diuji pada korpus realistis ≥10k halaman; saat ini korpus 44 dokumen / ~200 halaman. Cold-start ES Cloud setelah idle ≈ 3–5 detik. |
| c | Typo tolerance | ❌ | Query saat ini pakai `match`/`match_phrase_prefix` tanpa `fuzziness`. Harus aktifkan `fuzziness: "AUTO"` dan/atau analyzer dengan edge n-gram. |
| d | Filtering minimal 2 kata kunci | 🟡 | Mode `flexible` sudah `operator: AND` untuk multi-kata di konten, dan wildcard pada `filename` (boost 5×). Belum ada **filter berbasis field terpisah** (mis. `publish_date` range, klasifikasi, instansi pengirim). Mode frasa eksak (`"…"`) sudah berfungsi. |
| e | Perbandingan min 2 mesin pencarian | ❌ | Baru ada Elasticsearch. Perlu pembanding kedua: Meilisearch / Typesense / OpenSearch + endpoint paralel untuk demo side-by-side. |
| — | Bug: `/documents/search` selalu 502 | ✅ **FIXED** | Sebelumnya `collapse` dipakai di field `document_id` bertipe `text`. Diperbaiki dengan resolver dinamis `_resolve_collapse_field()` yang membaca mapping aktual dan memilih `document_id` (Cloud, sudah keyword) atau `document_id.keyword` (auto-mapping lokal). File: `app/services/document_search.py:14-39`. |

#### 1.1 *bis* — Pengukuran Awal (Preliminary Measurements)

Pengukuran ini bersifat indikatif (belum benchmark formal). Dilakukan pada 28 Mei 2026, korpus 44 dokumen di Elastic Cloud.

| Metrik | Nilai | Catatan |
|---|---|---|
| Search `pengelolaan` (warm, end-to-end BE) | **92 ms** | Browser → FastAPI → ES Cloud round-trip, termasuk serialisasi JSON. Diukur via `curl -w "%{time_total}"`. |
| Search `pengelolaan` (warm, FE termasuk render) | **~120–180 ms** | Diukur via `performance.now()` di hook `useSearch` (`sri_demo_fe/src/lib/hooks/useSearch.ts`), ditampilkan real-time di UI lewat `LatencyBadge`. |
| Health BE (`/health`) | ~5 ms | Lokal in-process. |
| Health ES Cloud (`/healthElasticsearch`) | ~150–300 ms (warm) · 3–5 s (cold) | Network RTT ke `asia-southeast2.gcp`. |
| Index ES (44 dokumen, 1 PDF ≈ 5 halaman) | 1.5–3 s/dokumen (BG task) | Tika ekstraksi + ES bulk index, di luar critical path search. |

**Gap menuju target KAK §2.9.b (< 100 ms):** angka 92 ms saat ini sudah berada di bawah ambang, tetapi pada korpus mini. Untuk klaim yang valid di evaluasi tender, perlu uji ulang dengan korpus minimal **10.000 halaman** dan target **P95 < 100 ms**, plus profil cold-start (warm-up routine atau ES Cloud paid tier dengan dedicated node).

### 1.2 AI Metadata Extraction — Otomatisasi Input Naskah *(5 menit)*

| # | Requirement KAK | Status | Catatan |
|---|---|---|---|
| a | Parsing dokumen | ✅ | Tika 3.3 sudah parse PDF (text per halaman). |
| b | Ekstraksi otomatis *field dynamic metadata* | 🟡 | **Layer 1 (regex) + Layer 2 (NER) hybrid sudah berjalan** — `app/services/metadata_extraction.py`. <br>**Layer 1**: 10 field strict-format (nomor_surat, sifat, lampiran, perihal, tempat, tanggal ISO+raw, penerima, klasifikasi_code, NIP). Latency < 5 ms. Hasil korpus uji: 9/10 field di dummy tim dev (conf 0.85). <br>**Layer 2** (aktif via `?use_ner=true`): NER Bahasa Indonesia (spaCy `id_ner_spacy_indonesian` — model komunitas, 19 entity labels, **bukan** fine-tuned IndoBERT) untuk 5 field free-form: `instansi_pengirim`, `organisasi_disebut`, `lokasi_disebut`, `fasilitas_disebut`, `regulasi_disebut`. Plus filter heuristik domain-specific untuk membuang noise (gelar, akronim, kode klasifikasi yang ke-tag salah). Latency +13–35 ms warm, +2.5 s cold (warm-up otomatis saat startup). RAM tambahan ~200 MB. Lihat §1.2 *bis* untuk roadmap upgrade ke IndoBERT fine-tuned. |
| c | REST API untuk integrasi ke frontend | ✅ | Tiga endpoint tersedia: `POST /metadata/extract?use_ner=true`, `GET /metadata/extract/by-document/{id}?use_ner=true`, dan v1 `GET /api/v1/arsip/{id}/metadata?use_ner=true`. Default `use_ner=false` untuk backward compatibility (tidak break klien lama). Response Pydantic terstruktur dengan confidence per field, plus `ner_entities` raw untuk transparansi/debugging. FE `sri_demo_fe` siap menampilkan hasil. |

#### 1.2 *bis* — Pendekatan yang Direkomendasikan untuk Naskah Dinas

Naskah dinas pemerintah Indonesia memiliki struktur sangat predictable (header `Nomor:`, `Sifat:`, `Lampiran:`, `Perihal:`, `Yth.`, tanggal tempat-Jakarta, tanda tangan dengan jabatan). Karakteristik ini sangat menguntungkan pendekatan **NLP terstruktur**, bukan LLM generatif.

**Mengapa NLP mini-model lebih tepat dari LLM API untuk konteks ANRI:**

| Aspek | LLM API (GPT/Claude/Gemini) | NLP/NER mini-model on-prem |
|---|---|---|
| Data sovereignty | ❌ Data naskah dinas keluar ke server luar negeri | ✅ Tetap di infrastruktur ANRI |
| Latency per dokumen | 2–5 detik | < 50 ms (CPU saja, ONNX-exported) |
| Biaya marginal | ~$0.001–0.01 per dokumen × juta dokumen | ~$0 setelah training |
| Determinisme | Bisa halusinasi, format tidak konsisten | Deterministik + confidence score per entitas |
| Auditability | Black box, sulit pertanggungjawaban | Posisi token + score tiap entitas dapat di-trace |
| Kepatuhan SPBE | Bermasalah (kelola data sensitif via pihak ketiga) | Aman |

**Arsitektur pipeline yang direkomendasikan:**

```
PDF → Tika (sudah ada)
       ↓ raw text + posisi
   [1. Rule-based regex]      ← 80–90% kasus standar
       │   NOMOR_SURAT, TANGGAL, LAMPIRAN, SIFAT, PERIHAL, KLASIFIKASI
       ↓ residual text
   [2. NER fine-tuned IndoBERT] ← edge cases & field free-form
       │   PENGIRIM, PENERIMA, NAMA_JABATAN, NAMA_INSTANSI, TANDATANGAN
       ↓
   [3. Normalisasi]            ← "28 Mei 2026" → "2026-05-28"; "UM.01" → master Perka
       ↓
   [4. Validasi + confidence] ← bila nomor tidak match format → flag manual review
       ↓
   {metadata terstruktur JSON} → Postgres + ES
```

**Kandidat model untuk Bahasa Indonesia (urutan rekomendasi):**

| Model | Params | Cocok untuk | Sumber |
|---|---|---|---|
| **IndoBERT-base** (`indobenchmark/indobert-base-p1`) | 110 M | Token classification (NER), fine-tunable | HuggingFace |
| **IndoBERT-Lite** | 22 M | Edge deployment, latency super rendah | HuggingFace |
| **NusaBERT** | 110 M | Multi-bahasa Nusantara | HuggingFace |
| **XLM-RoBERTa-base** | 270 M | Baseline multilingual | HuggingFace |
| **spaCy `id_core_news_lg`** | ~50 MB | Quick start, entity terbatas (PER/LOC/ORG) | spaCy |
| **LayoutLMv3** | 130 M | Bila perlu spatial cues (mis. nomor di pojok kanan atas halaman) | Microsoft |

**LLM API hanya dipakai sebagai fallback atau enrichment** (mis. ringkasan, klasifikasi semantik halus), bukan jalur ekstraksi utama. Untuk PoC, layer regex saja sudah cukup mendemonstrasikan ekstraksi 80% kasus; layer NER ditambahkan jika waktu memungkinkan.

**Effort realistis untuk implementasi PoC:**

| Langkah | Effort | Status |
|---|---|---|
| Pipeline regex + endpoint `/metadata/extract` | 1 hari | ✅ **Selesai 2026-05-28** |
| Endpoint retrofit `/metadata/extract/by-document/{id}` | 0.3 hari | ✅ **Selesai 2026-05-28** |
| Integrasi Layer 2 ke pipeline (hybrid regex + NER spaCy ID) | 0.5 hari | ✅ **Selesai 2026-05-31** |
| Bangun corpus anotasi 200–500 naskah dinas (Doccano / Label Studio) | 3–5 hari (1 anotator) | ⏳ Pending |
| Fine-tune IndoBERT untuk 8–10 entity classes domain naskah dinas | 1–2 hari | ⏳ Pending |
| Swap spaCy NER → IndoBERT fine-tuned (interface sudah stabil di `ner_indonesian.py`) | 0.3 hari | ⏳ Pending |
| Validasi + confidence threshold + flag manual review | 0.5 hari | ⏳ Pending |
| Integrasi ke pipeline upload (`pdf_ingest.py` setelah Tika) | 0.5 hari | ⏳ Pending |
| **Sisa effort** | **~5–7 hari** | |

**Catatan deployment Layer 2 yang sudah live (spaCy `id_ner_spacy_indonesian`):**
- **Tidak perlu Docker.** Cukup `pip install spacy` + 1 wheel model dari HuggingFace (lihat `requirements.txt`). Model dimuat in-process di uvicorn yang sama (singleton, lazy-load, thread-safe — lihat `app/services/ner_indonesian.py`).
- **RAM**: +~200 MB di steady state (terukur dengan `resource.getrusage`).
- **Disk**: ~50 MB di `venv/lib/.../id_ner_spacy_indonesian/`.
- **Latency**: 13–35 ms/halaman A4 di Apple Silicon (warm). Cold start ~2–2.5 s — dihindari dengan **warm-up otomatis** saat startup uvicorn (`NER_WARMUP=1`, default on).
- **Graceful degrade**: bila wheel model tidak ter-install, request `?use_ner=true` tetap 200 OK dengan `ner_available: false` dan Layer 1 tetap jalan. Tidak memecahkan kontrak API.
- **Offline-capable**: tidak ada call internet runtime. Cocok untuk data sovereignty ANRI.

**Keterbatasan jujur (untuk dokumentasi internal — jangan over-claim ke evaluator):**
- Model dilatih di korpus berita umum, bukan naskah dinas pemerintah. Beberapa entitas form (`Sifat`, `Nomor`, klasifikasi code seperti `KU - Keuangan`) **kadang ke-tag salah** sebagai ORG/FAC/GPE — dimitigasi dengan filter heuristik domain-specific (whitelist indikator institusional, blacklist gelar/akronim singkat, whitelist keyword regulasi).
- Field **PENGIRIM (nama orang)** belum di-classify ke field naskah dinas terpisah karena PER detection di model komunitas ini tidak konsisten untuk format formal (gelar akademik + tanda tangan). Workaround: gunakan jangkar NIP yang sudah ada di Layer 1.
- Untuk akurasi 90%+ pada domain naskah dinas spesifik, **iterasi berikutnya** harus fine-tune model BERT-based (IndoBERT / IndoBERT-Lite / IndoBERTweet) di corpus terlabel ANRI ≥ 200 dokumen. Interface `ner_indonesian.py` sudah siap untuk swap.

### 1.3 Async Processing & Dynamic Watermark *(10 menit)*

| # | Requirement KAK | Status | Catatan |
|---|---|---|---|
| Async | Generate laporan PDF/Excel | ❌ | Belum ada generator laporan (kandidat: WeasyPrint/ReportLab + openpyxl). |
| Async | Proses berjalan *background job* | 🟡 | Pakai `BackgroundTasks` FastAPI (in-process). Untuk produksi skala 15k–20k user perlu Celery/RQ/Arq dengan Redis/RabbitMQ. |
| Async | User menerima notifikasi | ❌ | Tidak ada mekanisme notifikasi (WebSocket/SSE/push/email). |
| Async | File tersimpan di MinIO | ❌ | Saat ini disimpan di local filesystem (`storage/documents/...`). Perlu integrasi S3-compatible (MinIO). |
| Watermark | Watermark DRAFT, BELUM DIKIRIM, hilang setelah pengiriman, validasi TTE tetap sah | ❌ | Belum ada modul watermark/TTE. |

### 1.4 Sub-PoC lain (di luar scope utama repo ini)

| Sub-PoC | Status repo | Catatan |
|---|---|---|
| Integrasi Layanan (API, skema metadata interop, error checking, jejak aktivitas) | ✅ | **PoC interoperabilitas selesai (2026-05-31).** Public API v1 di `/api/v1/*` lengkap dengan: (1) **versioned path** untuk stabilitas kontrak; (2) **response envelope seragam** `{status, data, meta}` / `{status, error, meta}`; (3) **error handling terpusat** dengan 15 kode error stabil di `/api/v1/errors`; (4) **audit log** otomatis tiap request (`logs/audit.log` JSON-Lines, viewable via `GET /api/v1/audit-log`); (5) **request correlation** via header `X-Request-ID` & `X-Response-Time-Ms`; (6) **OpenAPI 3.1 spec** auto-generated di `/openapi.json`, dirender sebagai **Swagger UI** di `/docs` dan **ReDoc** di `/redoc` — siap diimport ke Postman/Insomnia/codegen oleh konsumen eksternal. File: `app/api_v1/`. |
| JRA Dashboard — Monitoring Retensi Arsip | 🟡 | **Prototype FE tersedia** di `sri_demo_fe/src/pages/JraDashboardPage.tsx` (tab "Retensi (JRA)") sebagai bukti UX/UI: KPI cards (aktif/inaktif/musnah/permanen), banner peringatan (overdue + mendekati jatuh tempo + menunggu persetujuan), pipeline penyusutan 6-tahap, line chart tren 12 bulan (SVG murni), distribusi per klasifikasi (Perka ANRI: KU/KP/HK/OT/PR/HM/TI/UM/PL/PW), dan tabel arsip perlu tindakan. **Data masih simulasi** (`src/lib/mock/jraData.ts`) — backend retensi (engine penghitung jatuh tempo, workflow persetujuan musnah sesuai PP 28/2012 ps. 65) belum diimplementasi. |
| Penyusutan Arsip Elektronik | ➖ | Modul pemusnahan & lifecycle (KAK §2.1 #14, #15, #16). |
| Standar Keamanan Aplikasi Web (BSSN) | ❌ | Repo belum ada auth — tidak ada login, JWT, password hashing, lockout, HSTS, rate limit. Untuk PoC keamanan, harus dibangun terpisah atau sebagai bagian dari aplikasi utama. |
| Standar Keamanan Mobile (Android/iOS) | ➖ | Repo ini backend + web, mobile di luar scope. |
| Pengetahuan Tentang Kearsipan | ➖ | Presentasi/diskusi, bukan kode. |

### 1.5 Frontend Companion (`sri_demo_fe`) — Bukti UX untuk §2.9

Repo frontend dibuat untuk **mendemonstrasikan secara visual** kapabilitas backend di hadapan evaluator. Frontend adalah SPA (Single-Page Application) murni; tidak menambah beban server.

**Stack & ukuran**
- **Vite 8** + **React 19** + **TypeScript strict** + **React Router 7** (mode SPA) + **Tailwind 4**.
- Bundle produksi: **303 KB JS** (96 KB gzipped) + 21 KB CSS (5 KB gzipped). Build time: **117 ms**.
- Dev server memori: ~150–250 MB (vs Next.js sebelumnya 600 MB – 1 GB) — dipilih agar PoC mudah dijalankan di laptop spesifikasi sedang.
- Arsitektur komponen mengikuti **SOLID** (lihat `sri_demo_fe/README.md`): tiap komponen punya tanggung jawab tunggal, page tidak tahu HTTP — pakai custom hooks (`useSearch`, `useUpload`) yang membungkus `lib/api.ts`.

**Pemetaan fitur FE ke requirement KAK §2.9**

| Requirement KAK §2.9 (Mesin Pencarian) | Bukti UX di FE | File |
|---|---|---|
| §2.9.a — Pencarian full-text | Halaman `/` dengan input search real-time, hasil dirender sebagai daftar `ResultCard` dengan highlight `<em>` warna kuning. | `pages/SearchPage.tsx`, `components/search/ResultCard.tsx` |
| §2.9.b — Response time < 100 ms | **`LatencyBadge`** menampilkan latensi setiap query secara live: hijau (cepat <200 ms), kuning (sedang <500 ms), merah (lambat ≥500 ms). Evaluator bisa langsung melihat angka di layar. | `components/search/LatencyBadge.tsx` |
| §2.9.c — Typo tolerance | (Belum — tergantung fix di BE.) UI siap menampilkan suggestion jika BE mengembalikan `did_you_mean`. | — |
| §2.9.d — Filtering ≥ 2 kata kunci | Input mendukung multi-term (operator AND di BE) dan **mode frasa eksak** via tanda kutip `"…"` yang otomatis terdeteksi. Mode aktif ditampilkan sebagai badge (`mode phrase` / `mode flexible`). | `components/search/SearchBar.tsx`, `components/search/SearchSummary.tsx` |
| §2.9.e — Perbandingan ≥ 2 mesin pencarian | (Belum — perlu BE menyediakan endpoint paralel.) Layout `TabNav` siap untuk tab tambahan "Engine A vs Engine B". | — |
| AI Metadata Extraction (sub-PoC 2) — REST API ke FE | Halaman `/upload` dengan dropzone parallel; setiap file menunjukkan status `queued → uploading → success/error`. Setelah BE menambahkan `/metadata/extract`, hasil ekstraksi akan ditampilkan inline pada `UploadItemRow`. | `pages/UploadPage.tsx`, `components/upload/UploadItemRow.tsx` |
| Async Processing (sub-PoC 3) — notifikasi user | Polling status indeks per dokumen via `GET /documents/{id}`; saat ini ditampilkan sebagai badge. UI siap untuk WebSocket/SSE bila BE ditambah. | `lib/api.ts:getDocument` |
| Operability (§1.5.3 — jejak aktivitas) | Header menampilkan dua **HealthPill** (API · ES) yang di-polling tiap 30 detik dari `/health` dan `/healthElasticsearch`. Memberi konteks operasional saat demo. | `components/layout/AppHeader.tsx` |

**Apa yang FE belum kerjakan (gap UX)**
- Halaman detail dokumen (membuka satu PDF + highlight per halaman).
- Filter berbasis field (date range, klasifikasi, instansi).
- Mode "compare two search engines" (menunggu §2.9.e di BE).
- Notifikasi push/SSE saat indeks selesai (saat ini polling).
- Internationalization (saat ini hanya Bahasa Indonesia hard-coded).

**Catatan deployment**
- FE bisa di-deploy ke Vercel/Netlify (static SPA, gratis). Build sudah lulus di Vercel pada commit `e9c2864`.
- **Untuk PoC dapat dicoba ANRI**, BE perlu dapat diakses publik. Saat ini BE jalan di laptop developer. Tiga opsi: (1) sesi demo live via screen share, (2) Cloudflare Tunnel untuk mem-publish BE laptop, (3) host BE+Tika di Render/Fly.io. Detail di §5.

---

## 2. Pemetaan ke KAK §1.5 & §2.1 — Persyaratan Umum/Khusus & Ruang Lingkup

Untuk konteks lebih luas, KAK juga menuntut hal-hal arsitektur/operasional yang bisa mempengaruhi penilaian PoC.

| Klausa | Persyaratan | Status repo `sri_demo_be` | Catatan |
|---|---|---|---|
| §1.3 | Arsitektur microservices | 🟡 | Repo ini **adalah satu microservice** dalam konteks SRIKANDI: *Search & Document Ingestion Service*. Tidak monolitik karena hanya menangani 1 *business capability*, dengan datastore terpisah (Postgres untuk metadata, ES Cloud untuk full-text index, Tika sebagai dependency ekstraksi). Yang **belum** terlihat di PoC ini: (a) service domain lain (Auth, Retensi/JRA, Notifikasi, Watermark/TTE, AI Metadata) sebagai bukti pemecahan kapabilitas; (b) service mesh / API gateway; (c) message bus untuk komunikasi async antar-service. Catatan penting: **ES Cloud, Tika, dan Postgres adalah infrastruktur**, bukan microservice domain — mirip Redis/RabbitMQ — sehingga keberadaan mereka tidak otomatis berarti microservices, tapi menunjukkan separation of concerns yang sehat. |
┌────────────────────────────────────────────────────────────┐
│                        SRIKANDI System                      │
├────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Search     │  │  Document    │  │    Auth      │     │
│  │  Service     │  │   Service    │  │   Service    │ …   │
│  │ ← sri_demo   │  │              │  │              │     │
│  │   _be        │  │              │  │              │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │ pakai          │ pakai          │ pakai          │
│         ↓                ↓                ↓                 │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Infra: ES Cloud · Tika · Postgres · Redis · MinIO  │  │
│  └─────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
| §1.5.1.b | Uptime 99,75%/tahun, 24/7 | ➖ | Berlaku untuk produksi, bukan PoC. |
| §1.5.2.a | Skalabilitas + performa | ❌ | Belum ada uji beban. KAK §2.1.4 minta uji 15k normal / 20k stress concurrent users. PoC pencarian setidaknya perlu **bukti** bisa diskalakan (mis. via ES sharding). |
| §1.5.2.c–e | Open source, latest stable, security patch berkala | ✅ | FastAPI, Postgres, Elasticsearch, Tika, React, Vite — semua OSS / OSI-approved. Server ES kini pakai **Elastic Cloud 9.x** (managed, auto-patch). Versi lain: `fastapi==0.136.3`, `tika==3.3`, `psycopg2-binary==2.9`, `react==19`, `vite==8` — semua latest stable per Mei 2026. |
| §1.5.2.f | Log file untuk traceability | ✅ | Sudah ada `logs/app.log` dengan rotation harian (`app/logging_config.py`). |
| §1.5.3 | API interoperabilitas + skema metadata + error checking + jejak aktivitas | ✅ | **PoC v1 selesai (2026-05-31)** — lihat catatan lengkap di §1.4 baris "Integrasi Layanan". Ringkas: versioned path `/api/v1/*`, response envelope seragam, 15 kode error stabil terdokumentasi, audit log JSON-Lines + endpoint viewer, OpenAPI 3.1 + Swagger UI + ReDoc, request correlation via `X-Request-ID`. |
| §2.1.2.a | Anti SQL Injection | 🟡 | SQLModel + parameterized query → aman. Belum ada pembuktian eksplisit (mis. test SQLi). |
| §2.1.2.b | Weak password detection | ❌ | Tidak ada auth. |
| §2.1.2.c | Anti brute force (login lockout) | ❌ | Tidak ada auth. |
| §2.1.2.d–f | Standar BSSN, audit BSSN, WAF | ❌ | Belum ada. Untuk PoC pencarian, narasi WAF biasanya di sisi infra (NGINX + ModSecurity / Cloudflare). |
| §2.1.2.g | Patch security berkala | ❌ | Belum ada dokumen kebijakan patch atau dependency scanner (mis. Dependabot, `pip-audit`). |

---

## 3. Bug & Issue Konkret di Kode Saat Ini

| # | Severity | File | Masalah | Status / Fix |
|---|---|---|---|---|
| B-01 | 🔴 ~~Critical~~ | `app/services/document_search.py:14-39` | `collapse: {"field": "document_id"}` di field `text` → ES error `search_phase_execution_exception` → endpoint search **tidak bisa dipakai sama sekali**. | ✅ **FIXED (2026-05-28).** Resolver dinamis `_resolve_collapse_field()` membaca mapping aktual dan memilih `document_id` (ES Cloud, sudah keyword) atau `document_id.keyword` (auto-mapping). Endpoint search kini stabil. |
| B-02 | 🟠 High | `app/services/pdf_ingest.py:36-105` | Banyak `print(f"checcckkkkkkkkkkkk")`, debug strategy A/B/C/D, dan kode dead-code di dalam `_bulk_index_pages`. Mencemari log produksi. | ❌ Belum. Bersihkan: gunakan `logger.debug` jika perlu, hapus kode probing strategy. |
| B-03 | 🟠 ~~High~~ | `requirements.txt` | `python-multipart` tidak terdaftar tapi dibutuhkan FastAPI untuk endpoint `/upload`. | ✅ **FIXED.** `python-multipart==0.0.20` terdaftar di `requirements.txt`. |
| B-04 | 🟡 Medium | `app/routers/health.py:30-31` | `print(es.info())` di endpoint health → response besar di log setiap kali healthcheck. | ❌ Belum. Hapus print/log info. Cukup return `{"status": "ok", "cluster_name": ..., "version": ...}`. |
| B-05 | 🟡 Medium | `app/routers/health.py:22` | `return {"status": "ok mantap"}` — string informal di response API. | ❌ Belum. Standarkan: `{"status": "ok"}`. |
| B-06 | 🟡 Medium | `app/routers/documents.py:83-86` | File temporary disimpan di **CWD** dengan nama `temp_{uuid}_{filename}`. Race condition jika dua request bersamaan; juga bocor jika filename mengandung path separator. | ❌ Belum. Pakai `tempfile.NamedTemporaryFile` atau `tempfile.mkdtemp()`, dan sanitize filename. |
| B-07 | 🟢 ~~Low~~ | `README.md` | Instruksi PowerShell only, tidak ada panduan untuk macOS/Linux developer. | 🟡 Sebagian. Sudah ditambah panduan shell macOS di sesi setup; perlu di-commit ke README resmi. |
| B-08 | 🟢 Low | Indexing | Index ES tidak dibuat eksplisit (auto-mapping). Field `document_id` jadi `text+keyword` default. Tidak ada analyzer khusus (mis. untuk bahasa Indonesia). | ❌ Belum. Buat `index template` eksplisit dengan analyzer Indonesia (`indonesian` analyzer / ICU) dan mapping `keyword` untuk field identifier. **Catatan**: B-01 di-workaround dengan resolver dinamis; untuk produksi mapping eksplisit tetap rekomendasi terbaik. |
| B-09 | 🟢 Low | `main.py` (CORS) | `CORS_ALLOW_ORIGINS` default hanya port 3000 (Next.js). | ✅ **FIXED.** `.env` diperbarui agar mencakup port 5173 (Vite) dan 3000. Untuk produksi, ganti dengan domain Vercel/Cloudflare FE. |

---

## 4. Prioritas Aksi untuk Menyelesaikan PoC Pencarian

Asumsi: target presentasi PoC tender ANRI dengan checklist KAK §2.9 sub-2 (*Mesin Pencarian*). Effort dalam *person-days* kasar. ✅ = sudah selesai sejak Rev. 1.

| Prio | Aksi | Effort | Status | Hasil yang bisa didemo |
|---|---|---|---|---|
| ~~P0~~ | Fix bug B-01 (collapse field) | 0.1 d | ✅ **Done** | `/documents/search` berfungsi (sudah terbukti pada 28 Mei 2026). |
| ~~P0~~ | Dashboard sederhana untuk demo | 1 d | ✅ **Done** | Frontend SPA `sri_demo_fe` siap, deployable ke Vercel (komit `e9c2864`). |
| **P0** | Aktifkan `fuzziness: "AUTO"` di query content | 0.2 d | ⏳ Pending | Typo tolerance terpenuhi (KAK §2.9.c). |
| **P0** | Bangun mapping/index template eksplisit + analyzer Indonesia | 0.5 d | ⏳ Pending | Search relevant terhadap Bahasa Indonesia (stemming, stopword). Sekaligus menutup B-08. |
| **P0** | Bersihkan bug B-02 (logging spam) | 0.2 d | ⏳ Pending | Log produksi bersih. |
| **P0** | Generate korpus dummy ≥ 10.000 halaman + seed | 0.5 d | 🟡 Sebagian | Skrip `scripts/generate_corpus.py` & `seed_corpus.py` sudah ada; baru 200 dibangkitkan / 44 terindeks. Tinggal scale up + paralelisasi. |
| **P1** | Filter multi-field (tanggal range, filename, klasifikasi) | 0.5 d | ⏳ Pending | KAK §2.9.d "filtering minimal 2 kata kunci" terpenuhi penuh (saat ini sebagian via wildcard filename + AND content). |
| **P1** | Tambah Meilisearch / Typesense + endpoint `/search/v2` paralel | 1 d | ⏳ Pending | KAK §2.9.e "perbandingan min 2 mesin pencarian" terpenuhi. FE sudah siap untuk tab side-by-side. |
| **P1** | Benchmark Locust/k6 + laporan P50/P95 | 1 d | ⏳ Pending | Bukti formal KAK §2.9.b "< 100 ms" (saat ini ada angka informal 92 ms warm di korpus mini). |
| **P1** | Deployment public BE (Cloudflare Tunnel / Render / Fly.io) | 0.5–1 d | ⏳ Pending | ANRI bisa mencoba PoC dari URL yang dibagikan, tidak hanya saat sesi live. |
| **P2** | Halaman detail dokumen di FE (PDF viewer + highlight per halaman) | 1 d | ⏳ Pending | Demo UX end-to-end: cari → klik hasil → lihat highlight di dalam dokumen. |
| **P2** | Endpoint suggestion / `did_you_mean` | 0.5 d | ⏳ Pending | Mempertegas typo tolerance secara visual. |
| **P3** | Audit log per query + dokumen | 0.5 d | ⏳ Pending | KAK §1.5.3.b "catatan jejak aktivitas". |

**Sisa effort kasar: 5–6 hari kerja** untuk backend engineer + 1–2 hari frontend, agar PoC pencarian lulus checklist KAK §2.9 sub-2 secara penuh. Item P0 yang sudah selesai sebelumnya (B-01, dashboard) menggeser fokus iterasi berikutnya ke **bahasa Indonesia (analyzer + fuzzy)** dan **skala korpus**.

---

## 5. Rekomendasi untuk Diskusi dengan Tim Dev / Penyedia

1. **Konfirmasi scope repo ini.** `sri_demo_be` + `sri_demo_fe` difokuskan pada sub-PoC §2.9 *"Mesin Pencarian Berkecepatan Tinggi"*, dengan sentuhan §2.9 sub-PoC *AI Metadata Extraction* dan *Async Processing*. Sub-PoC lain (keamanan BSSN, mobile, JRA dashboard, integrasi penuh) di luar lingkup dan sebaiknya didemonstrasikan terpisah.
2. **Konfirmasi bahasa target.** Naskah dinas ANRI implisit Indonesian; ES index sebaiknya pakai analyzer `indonesian` (atau ICU + stemmer) untuk stemming yang benar. Ini saat ini gap (B-08).
3. **Konfirmasi korpus demo.** Untuk membuktikan §2.9.b *"< 100 ms"* secara meyakinkan, perlu data realistis **≥ 10.000 halaman**. Saat ini 44 dokumen / ~200 halaman. Skrip generator sudah ada di `scripts/generate_corpus.py`; bisa diparalelkan. Sumber data publik: https://www.anri.go.id.
4. **Pembanding kedua (§2.9.e).** Pilihan: Meilisearch (typo tolerance built-in, developer-friendly), Typesense (mirip Algolia), atau OpenSearch (fork ES, kompatibel mapping). Layout FE sudah siap untuk tab perbandingan side-by-side.
5. **Strategi deployment PoC.** Karena FE sudah live di Vercel sementara BE jalan di laptop developer, untuk evaluator dapat mencoba PoC mandiri perlu salah satu:
   - **Opsi A — Demo live screen share** (effort: 0): paling sederhana, tetapi tidak bisa dicoba mandiri.
   - **Opsi B — Cloudflare Tunnel** (effort: ±10 menit): BE laptop di-expose ke URL publik selama sesi. Cocok untuk demo terjadwal.
   - **Opsi C — Host BE + Tika ke cloud** (effort: 2–4 jam): Render/Fly.io free tier, Postgres ke Supabase/Neon, Tika sebagai sidecar container. Cocok untuk evaluasi 24/7 multi-hari.
6. **Pisahkan PoC pencarian dari PoC keamanan.** KAK sub "Standar Keamanan Aplikasi Web (BSSN)" jauh lebih besar dan tidak masuk akal disatukan di sini.
7. **Pertimbangkan analyzer + fuzzy bersamaan.** Mengaktifkan `fuzziness: "AUTO"` tanpa analyzer Indonesia akan menghasilkan hasil aneh untuk akar kata Bahasa Indonesia. Implementasikan kedua-duanya dalam satu iterasi (P0 di §4).

---

## 6. Lampiran: Komponen Repo Saat Ini

### 6.1 Backend (`sri_demo_be`)

```
app/
├── config.py              # Load env, init Elasticsearch client (ES Cloud)
├── database.py            # SQLModel engine + init_db (auto create_all)
├── logging_config.py      # Rotating file + console logger
├── models/
│   └── document.py        # SQLModel: Document (id, document_id, filename, status, ...)
├── routers/
│   ├── health.py          # GET /, /health, /healthElasticsearch
│   └── documents.py       # POST /upload, GET /documents/{id}, GET /documents/search
└── services/
    ├── document_db.py     # CRUD Postgres
    ├── document_search.py # ES query builder (B-01 FIXED via _resolve_collapse_field)
    ├── document_storage.py# Simpan file ke filesystem
    ├── pdf_ingest.py      # Background task: Tika → ES bulk index
    └── pdf_validation.py  # pypdf validation pre-upload
main.py                    # FastAPI entry + CORS + lifespan (setup_logging + init_db)
requirements.txt
docker-compose.yml         # tika (elasticsearch dinonaktifkan — pindah ke Cloud)
.env                       # config lokal — ELASTICSEARCH_URL=cloud, CORS_ALLOW_ORIGINS=5173,3000
```

**Stack terdeteksi**
- FastAPI 0.136.3 + uvicorn 0.48 + `python-multipart` 0.0.20
- SQLModel 0.0.38 + psycopg2-binary 2.9 + Postgres 18.1 (lokal, port 5437)
- Elasticsearch client 9.4 → **Elasticsearch Cloud 9.x** (region `asia-southeast2.gcp`, autentikasi via API key)
- Apache Tika 3.3 (Docker lokal, hanya saat `/upload`)
- pypdf 6.12 untuk validasi
- python-dotenv 1.2

### 6.2 Frontend (`sri_demo_fe`)

```
src/
├── main.tsx               # Bootstrap React + RouterProvider
├── router.tsx             # Definisi route (/, /upload)
├── App.tsx                # Shell layout + <Outlet />
├── index.css              # Tailwind 4 + theme + highlight ES (.es-highlight em)
├── pages/
│   ├── SearchPage.tsx     # KAK §2.9.a, b, d
│   └── UploadPage.tsx     # KAK §2.9 AI Metadata + Async
├── components/
│   ├── layout/            # AppHeader (HealthPill), TabNav
│   ├── ui/                # Spinner, Badge, Card (reusable, SOLID)
│   ├── search/            # SearchBar, ResultCard, ResultList,
│   │                      # SearchSummary, LatencyBadge (§2.9.b), EmptyState
│   └── upload/            # Dropzone, UploadItemRow
└── lib/
    ├── config.ts          # VITE_API_BASE_URL, debounce, latency thresholds
    ├── types.ts           # TypeScript types respon BE
    ├── api.ts             # fetch client (ApiError, searchDocuments, ...)
    ├── format.ts          # helper format
    └── hooks/
        ├── useDebounce.ts
        ├── useSearch.ts   # AbortController, latency measurement
        └── useUpload.ts   # Antrian upload paralel
vite.config.ts             # Vite + @tailwindcss/vite + React plugin + alias @/*
tsconfig.app.json          # TypeScript strict, paths-relative-to-tsconfig
.env                       # VITE_API_BASE_URL=http://127.0.0.1:8000
```

**Stack terdeteksi**
- Vite 8 + React 19 + TypeScript 6 (strict)
- React Router 7 (mode SPA — library API, no SSR)
- Tailwind CSS 4 (`@tailwindcss/vite` plugin)
- **Build output:** 303 KB JS / 96 KB gzipped + 21 KB CSS / 5 KB gzipped, build dalam 117 ms
- **Memori dev server:** ~150–250 MB

### 6.3 Arsitektur runtime

```
[Browser Pengguna]
        │  (HTTPS)
        ▼
[Frontend SPA — Vercel atau localhost:5173]
        │  (HTTPS fetch, CORS dikonfigurasi)
        ▼
[Backend FastAPI — uvicorn :8000]
        ├──→ [PostgreSQL :5437]      ← status & metadata dokumen
        ├──→ [Apache Tika :9998]     ← hanya saat /upload (Docker)
        └──→ [Elasticsearch Cloud]   ← full-text index, region asia-southeast2.gcp
```

---

*Dokumen ini dibuat sebagai bahan diskusi & evaluasi teknis. Audiens utama Rev. 2: panitia/evaluator teknis ANRI pada tahap Evaluasi Teknis tender SRIKANDI 2026.*
