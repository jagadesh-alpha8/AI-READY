# Vector Store — College Evidence Retrieval

Semantic search over college document content, so a future benchmarking
criterion can retrieve the institution's own evidence and hand it to an LLM.

> **Architectural rule.** PostgreSQL remains the source of truth for every
> structured record. Pinecone holds only embeddings of document text plus the
> metadata needed to filter and cite them. Nothing here replaces a Django
> model, and no scoring, gap or recommendation logic was changed.

**This task built the retrieval layer only.** There are no benchmark criteria,
no benchmark vectors, no benchmark scores, and no comparison logic — the
benchmarking framework is still being prepared. See
[Connecting benchmarking later](#connecting-benchmarking-later).

---

## 1. Files

### Created

| File | Purpose |
|---|---|
| `apps/vector_store/models.py` | `VectorDocumentIndex` — per-document indexing status |
| `apps/vector_store/exceptions.py` | Recoverable/permanent taxonomy driving retry |
| `apps/vector_store/services/chunking.py` | Page-aware, sentence-aware chunking |
| `apps/vector_store/services/embeddings.py` | `EmbeddingService` ABC + OpenAI-compatible implementation |
| `apps/vector_store/services/pinecone_client.py` | The **only** module importing the Pinecone SDK; both store types + the mode detector |
| `apps/vector_store/services/indexer.py` | read → chunk → embed → upsert, plus the tracking row |
| `apps/vector_store/services/search.py` | `search_college_evidence()` |
| `apps/vector_store/tasks.py` | `index_document_vectors`, `index_sprint_vectors` |
| `apps/vector_store/views.py`, `serializers.py` | The three sprint-scoped endpoints |
| `apps/vector_store/tests.py` | 68 tests, Pinecone and embeddings faked |
| `apps/vector_store/migrations/0001_initial.py` | `VectorDocumentIndex` table |

### Modified

| File | Change |
|---|---|
| `config/settings.py` | `apps.vector_store` in `INSTALLED_APPS`; the `PINECONE_*` / `EMBEDDING_*` / `VECTOR_*` block |
| `apps/sprints/urls.py` | Mounts the three endpoints alongside the other sprint sub-resources |
| `apps/extraction/tasks.py` | `_queue_vector_indexing()` after a job completes |
| `requirements/base.txt` | `pinecone>=5.0.0,<7.0.0` |
| `.env.example` | Documents every new variable |

**Nothing else was touched.** The CRI engine, gap detectors, recommendation
generators and report builder are untouched.

---

## 2. How indexing works

```
Document (already uploaded & extracted)
   │
   ├─ PDFPageReader          reuses the extraction pipeline's own reader
   │                         → [{page_number, text}, ...]
   ├─ chunk_pages()          clean → split, never across a page,
   │                         never mid-sentence, with overlap
   │                         → [{chunk_index, page_number, text}, ...]
   ├─ generate_embeddings()  one batched call per 64 chunks
   ├─ build_vector_id()      college_{c}_document_{d}_chunk_{n}
   ├─ build_vector_metadata() isolation + traceability fields
   ├─ store.upsert()         overwrite in place, never duplicate
   ├─ _delete_stale()        drop chunks a shorter revision no longer has
   └─ VectorDocumentIndex    status / vector_count / model / hash / error
```

Triggered two ways, both asynchronous — **no HTTP request ever waits for
embedding generation**:

1. **Automatically**, when an extraction job finishes
   (`apps/extraction/tasks.py::_queue_vector_indexing`).
2. **On demand**, via `POST /vector-index`.

### Why a separate Celery task, not an 8th pipeline stage

`ExtractionJob.Step` is a fixed seven-value contract the AI Processing Monitor
renders against. Indexing also has its own retry budget and its own failure
meaning. Keeping them separate means **a Pinecone outage cannot fail an
extraction job that otherwise succeeded** — the call is wrapped so that even an
unexpected error is logged and swallowed.

### What is stored

Only the chunk text and the fields needed to filter or cite it. Original files
are never uploaded to Pinecone.

```json
{
  "college_id": "…", "sprint_id": "…", "document_id": "…",
  "document_type": "faculty_master_list",
  "document_name": "Faculty_Report.pdf",
  "page_number": 17, "chunk_index": 4,
  "text": "The institution has 312 faculty members…",
  "source_type": "college_document"
}
```

`checksum`, `file_size`, `mime_type`, `status` and other PostgreSQL columns are
deliberately **not** copied — a second copy nothing filters on can only drift.

---

## 3. College isolation

Three layers, and the innermost one cannot be bypassed by application code:

1. **API** — every endpoint resolves its sprint through
   `get_authorized_sprint()`, the same institution check the rest of the nested
   sprint routes use. The institution searched is taken from **the sprint in
   the URL**, never from the request body, so changing a payload value cannot
   reach another college.
2. **Filter construction** — `search.build_filter()` always sets
   `college_id`, and pins `source_type` to `college_document` so future
   benchmark vectors in the same index can never appear in these results.
3. **Pinecone** — the filter is applied **server-side**. Results are never
   filtered after retrieval. `PineconeVectorStore.query()` raises if handed an
   empty filter, so the guarantee does not depend on every caller remembering.

Optional narrowing: `sprint_id`, `document_type`, `document_ids`.

---

## 4. Re-indexing and idempotency

Vector IDs are deterministic — `college_{c}_document_{d}_chunk_{n}` — so
re-processing the same document **overwrites** rather than duplicating.

| Situation | Behaviour |
|---|---|
| Same text, same embedding model | No-op. Content hash matches → no re-embed, no upsert |
| Text changed | Re-embedded and upserted over the same IDs |
| Embedding model changed | Re-embedded (the recorded model no longer matches) |
| Document replaced with **fewer** chunks | Vectors `new_count … old_count-1` deleted |
| Document now has no text | `indexed`, `vector_count=0`, previous vectors pruned |
| `force=true` | Re-embeds regardless |

The content hash is over the **extracted text**, not the file: a re-upload that
differs only in PDF metadata should not cost a re-embed, and a file whose text
extraction improved should.

Obsolete-chunk cleanup derives the stale IDs from `vector_count` on the
tracking row. That works on every index type including serverless, where
delete-by-metadata-filter is unavailable. The trade-off: it trusts that row. If
it were lost, orphans would survive — still correctly scoped by metadata, so at
worst over-retrieval of the same document, never a cross-institution leak.

---

## 5. API

All three are nested under a sprint and require a bearer token.

### `POST /api/v1/sprints/{sprint_id}/vector-index`
Queue every **processed** document in the sprint. Role: `CanManageSprint`
(`super_admin` / `consultant` / `institution_admin`).

```jsonc
// request
{ "force": false }

// 202 Accepted
{
  "queued": 3,
  "documents": [
    { "id": "…", "document_name": "Faculty_Report.pdf", "status": "pending",
      "vector_count": 0, "embedding_model": "", "indexed_at": null }
  ]
}
```

### `GET /api/v1/sprints/{sprint_id}/vector-index/status`
Indexing status per document. Any institution member.

```jsonc
[
  { "id": "…", "document_name": "Faculty_Report.pdf", "document_type": "faculty_master_list",
    "status": "indexed", "vector_count": 42,
    "embedding_model": "text-embedding-3-small",
    "content_hash": "9f2b…", "indexed_at": "2026-09-04T06:31:12Z", "error_message": "" }
]
```

### `POST /api/v1/sprints/{sprint_id}/evidence-search`
Semantic search over this college's indexed content. Any institution member
(it is a read).

```jsonc
// request
{
  "query": "AI certified faculty and faculty AI training",
  "top_k": 5,
  "document_type": "faculty_master_list",   // optional
  "scope_to_sprint": true                   // default true; false = all sprints
}

// 200 OK
{
  "query": "AI certified faculty and faculty AI training",
  "count": 2,
  "results": [
    {
      "score": 0.89,
      "text": "The institution has 312 faculty members, of whom 18 hold AI certifications…",
      "document_id": "3fc78b7b-…",
      "document_name": "Faculty_Report.pdf",
      "document_type": "faculty_master_list",
      "page_number": 17,
      "chunk_index": 4,
      "sprint_id": "…",
      "institution_id": "…"
    }
  ]
}
```

**Status codes:** `400` bad query · `401` no token · `403` wrong institution or
role · `503` Pinecone unconfigured, or a transient provider failure (the body
says which).

No Pinecone credential, index name, host or raw match object is ever returned.

---

## 5a. Two kinds of Pinecone index

Pinecone indexes come in two shapes, and they use **different APIs**. Both are
supported; `PINECONE_EMBEDDING_MODE` picks, and `auto` (the default) asks the
index itself once per process.

| | Integrated | Manual |
|---|---|---|
| Index created with | an `embed` config (e.g. `llama-text-embed-v2`) | a plain `dimension` |
| Who embeds | **Pinecone, server-side** | this app |
| Write API | `upsert_records()` — records carry text | `upsert()` — records carry vectors |
| Read API | `search()` — embeds the query itself | `query(vector=…)` |
| Embedding key needed | **No** | Yes (`EMBEDDING_API_KEY`) |
| Query/stored model match | guaranteed by Pinecone | your responsibility |

`indexer` and `search` read `store.handles_embedding` and skip building an
embedding service entirely when the index owns it. Everything else — the
deterministic IDs, the metadata, the pruning, the isolation filter, the error
taxonomy — is shared.

> **Verified against a live index.** Two things only a real call surfaces:
> `namespace='__default__'` is rejected with a 400 by API versions before
> 2025-04 (use `''`, which is the default on every version), and Pinecone's
> exception `str()` includes the HTTP header dump — so classifying retryability
> by keyword matched `Connection: keep-alive` and made a permanent 400 look
> transient. Both are fixed and covered by regression tests.

---

## 6. Configuration

| Variable | Purpose | Required? | Default |
|---|---|---|---|
| `PINECONE_API_KEY` | Pinecone key | for the feature | — |
| `PINECONE_INDEX_NAME` | Index to read/write | for the feature | — |
| `PINECONE_CLOUD` | Cloud for index **creation** | no | `aws` |
| `PINECONE_REGION` | Region for index **creation** | no | `us-east-1` |
| `PINECONE_NAMESPACE` | Optional namespace (`""` = Pinecone's default) | no | `""` |
| `PINECONE_EMBEDDING_MODE` | `auto` \| `integrated` \| `manual` | no | `auto` |
| `EMBEDDING_API_KEY` | Embedding key; falls back to `OPENAI_API_KEY`/`AI_API_KEY` when usable. **Not needed for an integrated index** | manual mode only | — |
| `EMBEDDING_MODEL` | Embedding model | no | `text-embedding-3-small` |
| `EMBEDDING_DIMENSIONS` | Override for an unknown model | no | derived |
| `EMBEDDING_BASE_URL` | OpenAI-compatible endpoint | no | `""` |
| `VECTOR_CHUNK_MAX_CHARS` | Max chunk size | no | `1200` |
| `VECTOR_CHUNK_OVERLAP_CHARS` | Overlap; **must be < max** | no | `150` |
| `VECTOR_CHUNK_MIN_CHARS` | Below this a chunk is page furniture | no | `40` |
| `VECTOR_INDEX_MAX_RETRIES` | Celery retries | no | `3` |
| `VECTOR_INDEX_RETRY_BACKOFF_SECONDS` | Base backoff (`n · 2ⁿ`) | no | `20` |
| `VECTOR_SEARCH_DEFAULT_TOP_K` | Default results | no | `5` |
| `VECTOR_SEARCH_MAX_TOP_K` | Hard ceiling | no | `50` |

> **Anthropic note.** Anthropic publishes no embedding endpoint. A deployment
> running Claude for extraction still needs an OpenAI-compatible key here —
> hence `EMBEDDING_API_KEY`. An `sk-ant-` key is explicitly rejected as an
> embedding key so the failure names the real problem instead of surfacing as a
> confusing 401.

### Creating the index

The app **reads** an existing index; it does not create one. Create it once,
with dimensions matching your embedding model
(`text-embedding-3-small` → **1536**, `-3-large` → **3072**), and **metric
`cosine`**.

Console: *Create index* → name → dimensions → cosine → serverless, matching
`PINECONE_CLOUD` / `PINECONE_REGION`.

Or via the SDK:

```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="…")
pc.create_index(
    name="aios-college-evidence",
    dimension=1536,                      # must match EMBEDDING_MODEL
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
)
```

> **Changing `EMBEDDING_MODEL` invalidates every stored vector** — a query
> embedded by one model is not comparable to vectors from another. Create a new
> index and re-index with `force=true`. `VectorDocumentIndex.embedding_model`
> records which model produced each document's vectors so the mismatch is
> visible rather than silent.

---

## 7. Running locally

```bash
pip install -r requirements/development.txt   # brings in pinecone
python manage.py migrate
```

Add to `backend/.env`:

```
PINECONE_API_KEY=…
PINECONE_INDEX_NAME=aios-college-evidence
EMBEDDING_API_KEY=sk-…
```

Redis and a worker must be running, since indexing is async:

```bash
celery -A config worker -l info --pool=solo    # --pool=solo on Windows
```

Then either upload and process a document as usual (indexing follows
automatically), or index an existing sprint:

```bash
curl -X POST http://localhost:8000/api/v1/sprints/<sprint_id>/vector-index \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"force": false}'
```

From a shell, bypassing HTTP and Celery entirely:

```python
from apps.documents.models import Document
from apps.vector_store.services import indexer, search

indexer.index_document(Document.objects.get(id="…"))          # synchronous
search.search_college_evidence(institution_id="…", query="AI certified faculty", top_k=5)
```

### Production

Set the same variables in `/opt/ai-ready/.env` (next to `docker-compose.yml`)
and redeploy. Both the `backend` and `celery` containers read that file, and
both need the values — the worker does the indexing. No compose change is
needed; `pinecone` ships in the image via `requirements/base.txt`.

---

## 8. Failure handling

| Failure | Behaviour |
|---|---|
| Pinecone unavailable / timeout / rate limit / 5xx | **Recoverable** → 3 retries at 20 s, 40 s, 80 s → row `failed` with the reason |
| Invalid API key, missing index, 4xx | **Permanent** → row `failed` immediately, no wasted retries |
| Embedding rate limit / timeout / 5xx | **Recoverable**, same backoff |
| Embedding 4xx or malformed response | **Permanent** |
| Empty document / no extractable text | `indexed`, `vector_count=0` — an honest terminal state, not retried forever |
| Unreadable format (non-PDF) | **Permanent**, with the reader's own explanation |
| Celery broker down | Row `failed` with "Could not reach the Celery broker"; the API still responds normally |
| **Any** vector failure during extraction | Logged and swallowed — extraction is never affected |

Nothing is silently ignored: every failure lands on `VectorDocumentIndex` and
is visible through the status endpoint. Logs record model, counts, durations
and error class — never keys, prompts, document text or vectors.

---

## 9. Backward compatibility

With Pinecone unconfigured, `indexer.is_enabled()` is `False` and:

* no Celery task is queued and no row is written;
* document upload, Drive import, extraction, fact review, gap detection, CRI
  scoring, baseline approval, recommendations and reports are untouched;
* the three endpoints answer `503` with a clear reason rather than `500`.

The Pinecone SDK is imported **lazily**, inside `PineconeVectorStore._get_index()`.
`apps.vector_store` is in `INSTALLED_APPS`, so an eager import would make
`pinecone` a hard requirement for the whole project. Verified: `manage.py
check` passes and the full suite runs with the package **not installed**.

---

## 10. Connecting benchmarking later

Not built, deliberately. When the framework is ready, it plugs in here:

```
Benchmark criterion  (yours, not built here)
        │
        ▼  semantic query text
search_college_evidence(institution_id=…, query=…, top_k=…)
        │
        ▼  scored, cited chunks
LLM reasoning        (yours)
        │
        ▼
gap → evidence → recommendation
```

What is already in place for it:

* `search_college_evidence()` — a stable, provider-agnostic entry point.
* Every result carries `document_name`, `page_number` and `chunk_index`, so the
  LLM can say *"according to Faculty_Report.pdf, page 17…"* rather than
  asserting something unsourced — this project's anti-hallucination rule.
* `source_type: "college_document"` is already filtered on, so benchmark
  vectors can share the index without either side seeing the other.
* `scope_to_sprint: false` searches everything the institution has uploaded,
  which is what a cross-sprint benchmark query wants.

Still to be decided by whoever builds it: where criteria live, whether their
text is embedded at all, and how an LLM verdict becomes a `GapItem`. **The
existing deterministic CRI engine is unchanged and must stay that way** — this
layer retrieves evidence; it does not score.
