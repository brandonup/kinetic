# KIN-255: Document Ingestion Pipeline — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task.

**Goal:** Port and adapt the document ingestion pipeline from FounderPanel — extract → chunk → embed → pgvector index — with per-stage status tracking, 3x exponential retry, and a thin TaskDispatcher abstraction over FastAPI BackgroundTasks.

**Architecture:** A linear pipeline (`extractor → chunker → embedder → indexer`) driven by `IngestionPipeline`, which owns status transitions on `knowledge_base_documents` and per-stage retry. A thin `TaskDispatcher` wraps FastAPI `BackgroundTasks` as the only coupling point to the job runner, enabling a one-file Celery migration later. The upload endpoint validates size at the API boundary; token count is checked post-extraction before chunking.

**Tech Stack:** Python 3.11+, FastAPI, `unstructured[all-docs]`, `tiktoken`, `openai` (SDK), `tenacity`, `supabase-py`, `python-multipart`

---

## Spec-Section Coverage Matrix

| Spec §Section | Task(s) | Status |
|---|---|---|
| §12 `knowledge_base_documents` schema | Task 1, 7, 9 | Covered |
| §13 `knowledge_base_chunks` schema | Task 5, 7 | Covered |
| RAG arch § Ingestion Pipeline | Tasks 2, 3, 4, 6, 7 | Covered |
| RAG arch § Upload limits (25 MB, 1M tokens) | Tasks 7, 9 | Covered |
| RAG arch § Document-level summary (ENRICHMENT_ENABLED) | Task 6 | Covered |
| PRD §7 KB & RAG — background + retry | Tasks 7, 8 | Covered |
| PRD §7 KB & RAG — stage tracking UI surface | Task 9 | Covered |
| ADR-001 § BackgroundTasks + thin abstraction | Task 8 | Covered |

---

## Task 1: Dependencies + Fixtures

**Files:**
- Modify: `requirements.txt`
- Modify: `tests/conftest.py`

**Steps:**

1. Add to `requirements.txt`:
   ```
   # Ingestion
   unstructured[all-docs]>=0.12
   tiktoken>=0.6
   openai>=1.14
   tenacity>=8.2
   python-multipart>=0.0.9
   ```

2. Add fixtures to `tests/conftest.py` (after existing fixtures):
   ```python
   import io
   from unittest.mock import AsyncMock, MagicMock, patch
   from uuid import uuid4

   @pytest.fixture
   def sample_pdf() -> bytes:
       """Minimal valid PDF bytes for ingestion tests."""
       return (
           b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
           b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
           b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
           b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
           b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td"
           b"(Hello world)Tj ET\nendstream endobj\n"
           b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
           b"xref\n0 6\ntrailer<</Size 6/Root 1 0 R>>\nstartxref\n0\n%%EOF"
       )

   @pytest.fixture
   def large_document() -> bytes:
       """Text document that exceeds the 1M token ingestion limit."""
       # ~250 chars ≈ ~60 tokens; repeat to exceed 1M tokens
       word = "The quick brown fox jumps over the lazy dog. " * 500
       # 500 * 60 tokens ≈ 30k tokens per repeat; 40 repeats ≈ 1.2M tokens
       return (word * 40).encode("utf-8")

   @pytest.fixture
   def oversized_file() -> bytes:
       """Binary blob that exceeds the 25 MB upload limit."""
       return b"x" * (25 * 1024 * 1024 + 1)

   @pytest.fixture
   def mock_embedding_service():
       """Returns a context manager that patches EmbeddingService.embed_batch."""
       from unittest.mock import patch

       def _make_embeddings(texts):
           return [[0.1] * 3072 for _ in texts]

       with patch(
           "app.services.ingestion.embedder.EmbeddingService.embed_batch",
           side_effect=_make_embeddings,
       ) as mock:
           yield mock

   @pytest.fixture
   def db_session():
       """
       Mock Supabase client for unit tests.
       Returns a MagicMock that stubs table/execute chain.
       """
       session = MagicMock()
       # Default: table().upsert().execute() returns success
       session.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{"id": str(uuid4())}])
       session.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
       session.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": str(uuid4())}])
       return session
   ```

3. Commit:
   ```bash
   git add requirements.txt tests/conftest.py
   git commit -m "chore: add ingestion dependencies and test fixtures (KIN-255)"
   ```

---

## Task 2: Text Extractor

**Files:**
- Create: `app/services/ingestion/__init__.py` (empty)
- Create: `app/services/ingestion/extractor.py`

**Implementation:** Use `unstructured.partition.auto.partition` with `bytes` input and `content_type` hint. Supported types per spec: `.pdf`, `.docx`, `.doc`, `.pptx`, `.ppt`, `.txt`, `.md`, `.csv`, `.xlsx`, `.xls`, `.rtf`, `.jsonl`.

```python
"""Text extraction via unstructured library."""
from __future__ import annotations
import io
import logging
from typing import Optional
from unstructured.partition.auto import partition

logger = logging.getLogger(__name__)

SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/rtf",
    "application/jsonl",
}

class UnsupportedFileTypeError(ValueError):
    pass

def extract_text(content: bytes, content_type: str, filename: str) -> str:
    if content_type not in SUPPORTED_MIME_TYPES:
        raise UnsupportedFileTypeError(f"Unsupported file type: {content_type}")
    try:
        elements = partition(
            file=io.BytesIO(content),
            content_type=content_type,
            metadata_filename=filename,
        )
        return "\n\n".join(str(el) for el in elements if str(el).strip())
    except UnsupportedFileTypeError:
        raise
    except Exception as exc:
        logger.error("Extraction failed for %s: %s", filename, exc)
        raise RuntimeError(f"Text extraction failed: {exc}") from exc
```

Commit: `feat: add text extractor using unstructured (KIN-255)`

---

## Task 3: Fixed-Size Chunker

**Files:**
- Create: `app/services/ingestion/chunker.py`

Target: ~500 tokens per chunk, ~50 token overlap. Use `tiktoken` with `cl100k_base` encoding (same encoding used by `text-embedding-3-large`). Paragraph-aware: split on double-newline boundaries; fall back to sentence split if paragraph exceeds 500 tokens.

```python
"""Fixed-size token-based chunker. ~500 tokens per chunk, ~50 overlap."""
from __future__ import annotations
import re
import logging
from dataclasses import dataclass
from typing import List
import tiktoken

logger = logging.getLogger(__name__)
CHUNK_TARGET_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50
ENCODING = "cl100k_base"

@dataclass
class Chunk:
    text: str
    chunk_index: int
    section_path: str | None
    page_range: str | None
    token_count: int

def count_tokens(text: str, enc: tiktoken.Encoding) -> int:
    return len(enc.encode(text))

def chunk_document(text: str, total_tokens: int) -> List[Chunk]:
    """Split text into fixed-size chunks with overlap."""
    enc = tiktoken.get_encoding(ENCODING)
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: List[Chunk] = []
    buffer: List[str] = []
    buffer_tokens = 0
    idx = 0

    def flush(buf: List[str], i: int) -> Chunk:
        joined = "\n\n".join(buf)
        return Chunk(
            text=joined,
            chunk_index=i,
            section_path=None,
            page_range=None,
            token_count=count_tokens(joined, enc),
        )

    for para in paragraphs:
        para_tokens = count_tokens(para, enc)
        if buffer and buffer_tokens + para_tokens > CHUNK_TARGET_TOKENS:
            chunks.append(flush(buffer, idx))
            idx += 1
            # Overlap: keep last paragraph(s) up to CHUNK_OVERLAP_TOKENS
            overlap: List[str] = []
            overlap_tokens = 0
            for prev_para in reversed(buffer):
                t = count_tokens(prev_para, enc)
                if overlap_tokens + t > CHUNK_OVERLAP_TOKENS:
                    break
                overlap.insert(0, prev_para)
                overlap_tokens += t
            buffer = overlap
            buffer_tokens = overlap_tokens
        buffer.append(para)
        buffer_tokens += para_tokens

    if buffer:
        chunks.append(flush(buffer, idx))

    return chunks
```

Commit: `feat: add fixed-size token chunker (KIN-255)`

---

## Task 4: Embedding Service

**Files:**
- Create: `app/services/ingestion/embedder.py`

Port `EmbeddingService` from `~/Projects/founder_panel/backend/app/services/ingestion/embedding_service.py`. Changes for Kinetic:
- Source key from `settings.PLATFORM_OPENAI_KEY` (not `OPENAI_API_KEY`)
- Model hardcoded to `settings.EMBEDDING_MODEL` (default `text-embedding-3-large`)
- Batch size, retry params from settings (`EMBEDDING_BATCH_SIZE`, `EMBEDDING_MAX_RETRIES`, etc.)
- No `get_model_for_use_case` (removed in Kinetic)

The FounderPanel class is a direct port — copy `EmbeddingService` and `embed_batch`/`_embed_single_batch` methods, update the key source and remove FounderPanel-specific imports.

Commit: `feat: port embedding service with platform key (KIN-255)`

---

## Task 5: pgvector Indexer

**Files:**
- Create: `app/services/ingestion/indexer.py`

Writes `knowledge_base_chunks` rows. All columns per schema §13. Scope columns (`project_id`, `agent_definition_id`) are passed through from the KB parent — the caller resolves them from `knowledge_bases` before calling the indexer.

```python
"""Writes chunks + embeddings to knowledge_base_chunks via Supabase."""
from __future__ import annotations
import asyncio
import logging
from typing import List, Optional
from uuid import UUID
from app.services.ingestion.chunker import Chunk
from app.core.config import settings

logger = logging.getLogger(__name__)

async def index_chunks(
    supabase,
    document_id: UUID,
    knowledge_base_id: UUID,
    project_id: Optional[UUID],
    agent_definition_id: Optional[UUID],
    chunks: List[Chunk],
    embeddings: List[List[float]],
) -> int:
    """Insert chunk rows into knowledge_base_chunks. Returns count inserted."""
    if len(chunks) != len(embeddings):
        raise ValueError(f"chunks/embeddings length mismatch: {len(chunks)} vs {len(embeddings)}")
    rows = [
        {
            "document_id": str(document_id),
            "knowledge_base_id": str(knowledge_base_id),
            "project_id": str(project_id) if project_id else None,
            "agent_definition_id": str(agent_definition_id) if agent_definition_id else None,
            "text": chunk.text,
            "embedding": embedding,
            "section_path": chunk.section_path,
            "page_range": chunk.page_range,
            "chunk_index": chunk.chunk_index,
            "embedding_model": settings.EMBEDDING_MODEL,
        }
        for chunk, embedding in zip(chunks, embeddings)
    ]
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_chunks").insert(rows).execute(),
    )
    if not result.data:
        raise RuntimeError(f"Failed to index chunks for document {document_id}")
    logger.info("Indexed %d chunks for document %s", len(rows), document_id)
    return len(rows)
```

Commit: `feat: add pgvector chunk indexer (KIN-255)`

---

## Task 6: Optional Document Summarizer

**Files:**
- Create: `app/services/ingestion/summarizer.py`

Called when `settings.ENRICHMENT_ENABLED` is true (default). Uses platform `PLATFORM_ANTHROPIC_KEY` + `call_llm` to generate a short document summary from the first ~2000 tokens of extracted text. Returns `None` on failure (non-fatal — enrichment failure does not fail ingestion).

```python
"""Optional document-level summary generation (ENRICHMENT_ENABLED)."""
from __future__ import annotations
import logging
from app.services.llm_client import call_llm
from app.core.config import settings

logger = logging.getLogger(__name__)
SUMMARY_PROMPT = (
    "Summarize the following document in 2-3 sentences. "
    "Focus on the main topic, key points, and intended audience.\n\nDocument:\n{text}"
)

def generate_summary(text: str) -> str | None:
    """Generate a 2-3 sentence document summary. Returns None on failure."""
    if not settings.ENRICHMENT_ENABLED:
        return None
    if not settings.PLATFORM_ANTHROPIC_KEY:
        logger.warning("PLATFORM_ANTHROPIC_KEY not set; skipping enrichment")
        return None
    try:
        # Use first 2000 chars (~500 tokens) to avoid large prompt
        snippet = text[:8000]
        return call_llm(
            messages=[{"role": "user", "content": SUMMARY_PROMPT.format(text=snippet)}],
            model=settings.CONVERSATION_COMPRESSION_MODEL,
            api_key=settings.PLATFORM_ANTHROPIC_KEY,
            max_tokens=200,
            timeout=20,
        )
    except Exception as exc:
        logger.warning("Enrichment failed (non-fatal): %s", exc)
        return None
```

Also add to `config.py`:
```python
ENRICHMENT_ENABLED: bool = True
```

Commit: `feat: add optional document summarizer (KIN-255)`

---

## Task 7: Pipeline Orchestrator

**Files:**
- Create: `app/services/ingestion/pipeline.py`

The core orchestrator. Owns all status transitions on `knowledge_base_documents`. Per-stage retry uses `INGESTION_RETRY_DELAYS` (60s, 300s, 900s — delays apply in background; for unit tests mock `asyncio.sleep`).

```python
"""
Ingestion pipeline orchestrator.

Stages: extracting → chunking → embedding → completed | failed
Retry: up to MAX_INGESTION_RETRIES per stage, with INGESTION_RETRY_DELAYS backoff.
Token limit: INGESTION_TOKEN_LIMIT tokens per document (checked after extraction).
"""
from __future__ import annotations
import asyncio
import logging
from uuid import UUID
from typing import Optional
from app.core.config import settings
from app.services.ingestion.extractor import extract_text
from app.services.ingestion.chunker import chunk_document, count_tokens
from app.services.ingestion.embedder import EmbeddingService
from app.services.ingestion.summarizer import generate_summary
from app.services.ingestion.indexer import index_chunks
import tiktoken

logger = logging.getLogger(__name__)

class TokenLimitExceeded(ValueError):
    pass

async def _update_status(supabase, document_id: UUID, **fields) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_documents")
            .update(fields)
            .eq("id", str(document_id))
            .execute(),
    )

async def run_ingestion(
    supabase,
    document_id: UUID,
    knowledge_base_id: UUID,
    project_id: Optional[UUID],
    agent_definition_id: Optional[UUID],
    file_content: bytes,
    filename: str,
    content_type: str,
) -> None:
    """Run full ingestion pipeline with per-stage retry."""
    retry_count = 0

    async def _run_with_retry(stage: str, coro):
        nonlocal retry_count
        for attempt in range(settings.MAX_INGESTION_RETRIES + 1):
            try:
                await _update_status(supabase, document_id, status=stage, error_stage=None)
                return await coro()
            except Exception as exc:
                if attempt < settings.MAX_INGESTION_RETRIES:
                    delay = settings.INGESTION_RETRY_DELAYS[attempt]
                    logger.warning(
                        "Stage %s failed (attempt %d/%d) for %s: %s. Retrying in %ds.",
                        stage, attempt + 1, settings.MAX_INGESTION_RETRIES, document_id, exc, delay,
                    )
                    retry_count += 1
                    await _update_status(supabase, document_id, retry_count=retry_count)
                    await asyncio.sleep(delay)
                else:
                    await _update_status(
                        supabase, document_id,
                        status="failed",
                        error_stage=stage,
                        error_message=str(exc)[:2000],
                        retry_count=retry_count,
                    )
                    raise

    # --- Stage: extracting ---
    async def _extract():
        text = extract_text(file_content, content_type, filename)
        enc = tiktoken.get_encoding("cl100k_base")
        total_tokens = len(enc.encode(text))
        if total_tokens > settings.INGESTION_TOKEN_LIMIT:
            raise TokenLimitExceeded(
                f"Document exceeds token limit: {total_tokens} > {settings.INGESTION_TOKEN_LIMIT}"
            )
        await _update_status(supabase, document_id, token_count=total_tokens)
        return text, total_tokens

    text, total_tokens = await _run_with_retry("extracting", _extract)

    # Optional enrichment (non-fatal, outside retry loop)
    summary = generate_summary(text)
    if summary:
        await _update_status(supabase, document_id, summary=summary)

    # --- Stage: chunking ---
    async def _chunk():
        return chunk_document(text, total_tokens)

    chunks = await _run_with_retry("chunking", _chunk)

    # --- Stage: embedding ---
    embedder = EmbeddingService()
    async def _embed():
        loop = asyncio.get_running_loop()
        texts = [c.text for c in chunks]
        return await loop.run_in_executor(None, lambda: embedder.embed_batch(texts))

    embeddings = await _run_with_retry("embedding", _embed)

    # --- Index chunks ---
    await index_chunks(
        supabase, document_id, knowledge_base_id,
        project_id, agent_definition_id, chunks, embeddings,
    )

    await _update_status(supabase, document_id, status="completed", retry_count=retry_count)
    logger.info("Ingestion complete for document %s (%d chunks)", document_id, len(chunks))
```

Commit: `feat: add ingestion pipeline orchestrator with retry (KIN-255)`

---

## Task 8: TaskDispatcher

**Files:**
- Create: `app/services/background.py`

Thin abstraction. One method: `dispatch(task_fn, *args, **kwargs)`. In MVP, delegates to FastAPI `BackgroundTasks`. Migration to Celery = swap this one class.

```python
"""
Thin background task abstraction.

MVP: FastAPI BackgroundTasks.
Migration to Celery/RQ: replace dispatch() body only.
"""
from fastapi import BackgroundTasks

class TaskDispatcher:
    def __init__(self, background_tasks: BackgroundTasks) -> None:
        self._bt = background_tasks

    def dispatch(self, fn, *args, **kwargs) -> None:
        """Enqueue fn(*args, **kwargs) for background execution."""
        self._bt.add_task(fn, *args, **kwargs)
```

Commit: `feat: add TaskDispatcher background abstraction (KIN-255)`

---

## Task 9: Upload Endpoint + Router

**Files:**
- Create: `app/api/routes/documents.py`
- Modify: `app/main.py` — include documents router

Upload endpoint: `POST /api/v1/documents/upload`. Validates 25 MB file size, creates `knowledge_base_documents` row with `status='pending'`, dispatches pipeline via `TaskDispatcher`.

```python
"""Document upload endpoint — POST /api/v1/documents/upload"""
import asyncio
import logging
from uuid import UUID, uuid4
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from app.auth.deps import CurrentUser, get_current_user
from app.core.config import settings
from app.services.background import TaskDispatcher
from app.services.ingestion.pipeline import run_ingestion
from app.db.supabase_client import get_supabase

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
logger = logging.getLogger(__name__)

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    knowledge_base_id: UUID = Form(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: CurrentUser = Depends(get_current_user),
):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB upload limit.")

    document_id = uuid4()
    supabase = get_supabase()

    # Look up scope columns from knowledge_bases
    loop = asyncio.get_running_loop()
    kb_result = await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_bases")
            .select("project_id, agent_definition_id")
            .eq("id", str(knowledge_base_id))
            .single()
            .execute(),
    )
    if not kb_result.data:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    kb = kb_result.data
    project_id = UUID(kb["project_id"]) if kb.get("project_id") else None
    agent_definition_id = UUID(kb["agent_definition_id"]) if kb.get("agent_definition_id") else None

    # Create pending document row
    await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_documents").insert({
            "id": str(document_id),
            "knowledge_base_id": str(knowledge_base_id),
            "title": file.filename or "Untitled",
            "file_type": file.content_type,
            "file_size_bytes": len(content),
            "status": "pending",
            "retry_count": 0,
        }).execute(),
    )

    dispatcher = TaskDispatcher(background_tasks)
    dispatcher.dispatch(
        asyncio.run,
        run_ingestion(
            supabase, document_id, knowledge_base_id,
            project_id, agent_definition_id,
            content, file.filename or "", file.content_type or "application/octet-stream",
        ),
    )

    return {"document_id": str(document_id), "status": "pending"}
```

Also create `app/db/supabase_client.py`:
```python
from functools import lru_cache
from supabase import create_client, Client
from app.core.config import settings

@lru_cache(maxsize=1)
def get_supabase() -> Client:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
```

Add to `app/main.py`:
```python
from app.api.routes.documents import router as documents_router
app.include_router(documents_router)
```

Commit: `feat: add document upload endpoint and wire router (KIN-255)`

---

## Task 10: Activate Jìan Tests

**Files:**
- Modify: `tests/test_ingestion.py`

Remove all `@pytest.mark.skip` decorators. Implement each test body:

- `test_document_processes_through_all_stages` — mock `extract_text`, `chunk_document`, `EmbeddingService.embed_batch`, `index_chunks`; call `run_ingestion`; assert `_update_status` called with `"completed"`.
- `test_chunks_are_indexed_in_pgvector` — call `index_chunks` with mock supabase; assert insert was called with correct shape (length, `embedding_model` field).
- `test_failed_stage_retries_up_to_3_times` — patch `embed_batch` to raise; mock `asyncio.sleep`; call pipeline; assert retry_count==3, final status=="failed".
- `test_retry_succeeds_on_second_attempt` — patch to fail once then succeed; assert status=="completed", retry_count==1.
- `test_after_3_failures_status_is_failed` — use `client` fixture + POST to upload; mock pipeline to fail; GET document; assert `status=="failed"`.
- `test_each_stage_transition_is_persisted` — spy on `_update_status` calls; assert called with extracting, chunking, embedding, completed in order.
- `test_document_over_1m_tokens_is_rejected` — patch `extract_text` to return text that counts > 1M tokens; assert `TokenLimitExceeded`, status=="failed", no chunks written.
- `test_file_over_25mb_is_rejected_at_upload` — POST `oversized_file` to `/api/v1/documents/upload`; assert 413.

Run: `pytest tests/test_ingestion.py -v`
Target: all pass, ≥80% coverage on `app/services/ingestion/`.

Commit: `test: activate Jìan ingestion test suite (KIN-255)`

---

## Done-When

- [ ] `pytest tests/test_ingestion.py -v` — all 8 tests pass, 0 skipped
- [ ] Coverage: `pytest tests/test_ingestion.py --cov=app/services/ingestion --cov-report=term-missing` ≥ 80%
- [ ] Schema cross-reference: every column written matches `docs/db-schema-spec.md` §12–13 exactly
- [ ] No `await` on sync Supabase calls — all wrapped in `run_in_executor`
- [ ] No silent swallowing on writes — all DB writes raise or log-and-raise on failure
- [ ] `TaskDispatcher.dispatch()` is the only call site for background jobs — no direct `BackgroundTasks.add_task`
