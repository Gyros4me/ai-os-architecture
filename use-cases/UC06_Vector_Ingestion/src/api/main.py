# src/api/main.py
"""
Scalable Vector Ingestion Service - API Principale
==========================================
FastAPI con tutti gli endpoint per:
- File upload (PDF, CSV, TXT)
- Semantic search
- DLQ management
- System monitoring
- Frontend dashboard
"""

import os
import sys
import logging
import json
import uuid
import mimetypes
import ipaddress
import socket
import re
import asyncio
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, unquote, quote

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Configurazione logging PRIMA di qualsiasi altra operazione
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Output a console
        logging.FileHandler('app.log')      # Output a file
    ]
)
logger = logging.getLogger(__name__)

# Aggiungi directory dei servizi al path di Python
service_path = Path(__file__).parent.parent / "services"
if str(service_path) not in sys.path:
    sys.path.insert(0, str(service_path))
    logger.info(f"Added {service_path} to Python path")

# Import servizi - utilizzando try-except per gestire errori
try:
    logger.info("Attempting to import embedder...")
    from services.embedder import SemanticEmbedder, EmbeddingBenchmark, get_default_embedder
    logger.info("Embedder imported successfully")
except ImportError as e:
    # Fallback import (normal)
    try:
        # Fallback: import relativo
        from ..services.embedder import SemanticEmbedder, EmbeddingBenchmark, get_default_embedder
        logger.info("Embedder imported using relative import")
    except ImportError:
        logger.error("Cannot import embedder module")
        SemanticEmbedder = None
        EmbeddingBenchmark = None
        get_default_embedder = None

try:
    logger.info("Attempting to import vector_store...")
    from services.vector_store import VectorStoreService, get_default_vector_store
    logger.info("Vector store imported successfully")
except ImportError as e:
    # Fallback import (normal)
    try:
        from ..services.vector_store import VectorStoreService, get_default_vector_store
        logger.info("Vector store imported using relative import")
    except ImportError:
        logger.error("Cannot import vector_store module")
        VectorStoreService = None
        get_default_vector_store = None

try:
    logger.info("Attempting to import processor...")
    from services.processor import DocumentProcessor
    logger.info("Processor imported successfully")
except ImportError as e:
    # Fallback import (normal)
    try:
        from ..services.processor import DocumentProcessor
        logger.info("Processor imported using relative import")
    except ImportError:
        logger.error("Cannot import processor module")
        DocumentProcessor = None

try:
    logger.info("Attempting to import dlq...")
    from services.dlq import get_dlq, FailureReason
    logger.info("DLQ imported successfully")
except ImportError as e:
    # Fallback import (normal)
    try:
        from ..services.dlq import get_dlq, FailureReason
        logger.info("DLQ imported using relative import")
    except ImportError:
        logger.error("Cannot import dlq module")
        get_dlq = None
        FailureReason = None

try:
    logger.info("Attempting to import magellano_client...")
    from services.magellano_client import get_magellano_client
    logger.info("MagellanoClient imported successfully")
except ImportError:
    try:
        from ..services.magellano_client import get_magellano_client
        logger.info("MagellanoClient imported using relative import")
    except ImportError:
        logger.warning("MagellanoClient not available — /rag/query will return fallback-only responses")
        get_magellano_client = None

try:
    from services.text_normalizer import normalize_extracted_text
except ImportError:
    try:
        from ..services.text_normalizer import normalize_extracted_text
    except ImportError:
        def normalize_extracted_text(value, compact=False):
            return str(value or "").strip() if compact else str(value or "")

# Configurazione
CONFIG = {
    "MAX_FILE_SIZE_MB": 50,
    "DEFAULT_CHUNK_SIZE": 1000,
    "DEFAULT_CHUNK_OVERLAP": 100,
    "DEFAULT_BATCH_SIZE": 50,
    "MAX_BATCH_SIZE": 100,
    "MAX_SEARCH_RESULTS": 100,
    "UPLOAD_TIMEOUT_SECONDS": 300,
    "ENVIRONMENT": os.environ.get("ENVIRONMENT", "development")
}

# Definizione dei tag per Swagger UI
openapi_tags = [
    {
        "name": "Frontend",
        "description": "Dashboard e interfaccia web",
    },
    {
        "name": "Health & Monitoring",
        "description": "Controllo stato e statistiche sistema",
    },
    {
        "name": "DLQ Management",
        "description": "Gestione Dead Letter Queue (fallimenti)",
    },
    {
        "name": "Document Ingestion",
        "description": "Caricamento e elaborazione documenti",
    },
    {
        "name": "Search & Query",
        "description": "Ricerca semantica e gestione documenti",
    },
    {
        "name": "Embedding Operations",
        "description": "Operazioni di embedding e benchmark",
    },
    {
        "name": "Utility",
        "description": "Endpoint di utilità e configurazione",
    },
    {
        "name": "RAG Magellano",
        "description": "Ralph 2-Tier RAG: MiniLM retrieval + Magellano 85k generation",
    },
]

# Inizializza app FastAPI con tag organizzati
app = FastAPI(
    title="Scalable Data Ingestion & Vector Store Service",
    description="Self-hosted semantic document processing with vector search",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=openapi_tags
)

# CORS middleware — origini configurabili via env var per sicurezza in produzione
_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "")
_allowed_origins = (
    [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
    if _allowed_origins_env
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    # Credentials only with an explicit origin allowlist ("*" + credentials is invalid/unsafe)
    allow_credentials=_allowed_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_frontend_assets(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith(("/static/app.js", "/static/style.css", "/static/index.html")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response

# Mount static files
static_dir = Path(__file__).parent.parent.parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

def _configured_visual_roots() -> List[Path]:
    roots = []
    for env_name in ("VISUAL_ASSET_ROOTS", "MAGELLANO_VISUAL_ASSET_ROOTS"):
        raw = os.environ.get(env_name, "")
        if not raw:
            continue
        for path in raw.replace(",", os.pathsep).split(os.pathsep):
            path = path.strip()
            if path:
                roots.append(Path(path).resolve())
    return roots


_visual_asset_roots = _configured_visual_roots() or [
    static_dir.resolve(),
    (Path.cwd() / "data").resolve(),
    (Path.cwd() / "data" / "visual").resolve(),
    (Path.cwd() / "assets").resolve(),
    (Path.cwd() / "uploads").resolve(),
]

# Inizializza servizi con error handling
try:
    logger.info("Initializing embedder...")
    embedder = get_default_embedder() if get_default_embedder else None
    logger.info("Embedder initialized successfully" if embedder else "Embedder initialization failed")
except Exception as e:
    logger.error(f"Failed to initialize embedder: {e}")
    embedder = None

try:
    logger.info("Initializing vector store...")
    vector_store = get_default_vector_store(embedder=embedder) if get_default_vector_store else None
    logger.info("Vector store initialized successfully" if vector_store else "Vector store initialization failed")
except Exception as e:
    logger.error(f"Failed to initialize vector store: {e}")
    vector_store = None

try:
    logger.info("Initializing DLQ...")
    dlq = get_dlq() if get_dlq else None
    logger.info("DLQ initialized successfully" if dlq else "DLQ initialization failed")
except Exception as e:
    logger.error(f"Failed to initialize DLQ: {e}")
    dlq = None

# Variabili globali per monitoring
app_start_time = datetime.utcnow()
processed_files = []
pdf_ingest_jobs: Dict[str, Dict[str, Any]] = {}
pdf_ingest_queue: Optional[asyncio.Queue] = None
pdf_ingest_workers: List[asyncio.Task] = []
pdf_ingest_lock: Optional[asyncio.Lock] = None
pdf_ingest_state_loaded = False
vector_document_count_cache: Dict[str, Dict[str, Any]] = {}


def get_vector_store():
    """Small accessor used by RAG routes and tests."""
    return vector_store


def _magellano_ready(status: Optional[str]) -> bool:
    return str(status or "").lower() in {"healthy", "ok", "ready", "running", "up"}


def _metadata_value(metadata: Dict[str, Any], *keys: str) -> Optional[Any]:
    for key in keys:
        value = metadata.get(key)
        if value is not None and value != "":
            return value
    return None


def _magellano_visual_base_url() -> str:
    return (
        os.getenv("MAGELLANO_VISUAL_BASE_URL")
        or os.getenv("MAGELLANO_URL")
        or "http://localhost:8004"
    ).rstrip("/")


def _is_pdf_result(source: Any, metadata: Dict[str, Any]) -> bool:
    doc_type = str(_metadata_value(metadata, "type", "content_type", "mime_type") or "").lower()
    return doc_type == "pdf" or str(source or "").lower().endswith(".pdf")


def _safe_asset_stem(filename: Any) -> str:
    stem = Path(str(filename or "")).stem or "document"
    return re.sub(r"[^\w\-\.]+", "_", stem)[:120]


def _visual_url_for_local_asset(asset_path: Path) -> str:
    return f"/visual/asset?path={quote(asset_path.as_posix(), safe='')}"


def _configured_pdf_source_roots() -> List[Path]:
    roots: List[Path] = []
    raw = os.getenv("PDF_SOURCE_ROOTS", "")
    if raw:
        for item in raw.replace(",", os.pathsep).split(os.pathsep):
            item = item.strip()
            if item:
                roots.append(Path(item).resolve())
    roots.extend([
        (Path.cwd() / "uploads").resolve(),
        (Path.cwd() / "data").resolve(),
        Path.cwd().resolve(),
    ])
    unique: List[Path] = []
    seen = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        unique.append(root)
    return unique


def _pdf_source_candidates(source: Any, metadata: Dict[str, Any]) -> List[Path]:
    names = [
        _metadata_value(metadata, "local_pdf_path", "pdf_path", "file_path", "source_path", "path"),
        source,
        unquote(str(source or "")),
        f"{_safe_asset_stem(source)}.pdf",
    ]
    candidates: List[Path] = []
    for name in names:
        if not name:
            continue
        raw = Path(str(name).strip().strip('"').strip("'"))
        if raw.suffix.lower() != ".pdf":
            continue
        if raw.is_absolute():
            candidates.append(raw)
        for root in _configured_pdf_source_roots():
            candidates.append(root / raw.name)
            candidates.append(root / raw)

    unique: List[Path] = []
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _find_local_pdf_source(source: Any, metadata: Dict[str, Any]) -> Optional[Path]:
    for candidate in _pdf_source_candidates(source, metadata):
        try:
            if candidate.is_file() and candidate.suffix.lower() == ".pdf" and candidate.stat().st_size > 0:
                return candidate
        except OSError:
            continue
    return None


def _render_missing_pdf_page_image_metadata(source: Any, page_num: int, metadata: Dict[str, Any]) -> Dict[str, Any]:
    if os.getenv("RAG_RENDER_MISSING_PDF_PAGE_IMAGES", "true").lower() not in {"1", "true", "yes", "on"}:
        return {}
    pdf_path = _find_local_pdf_source(source, metadata)
    if not pdf_path:
        return {}
    try:
        import fitz  # type: ignore
    except Exception as e:
        logger.warning(f"PyMuPDF not available for on-demand visual render: {e}")
        return {}

    safe_stem = _safe_asset_stem(source)
    output_dir = Path(os.getenv("VISUAL_EXPORT_ROOT") or (Path.cwd() / "data" / "visual")) / "pdf_pages" / safe_stem
    output_path = output_dir / f"page_{page_num:04d}.png"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        if not output_path.exists() or output_path.stat().st_size <= 0:
            doc = fitz.open(str(pdf_path))
            try:
                if page_num < 1 or page_num > doc.page_count:
                    return {}
                dpi = int(os.getenv("PDF_PAGE_IMAGE_DPI", "140"))
                matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
                pix = doc.load_page(page_num - 1).get_pixmap(matrix=matrix, alpha=False)
                pix.save(str(output_path))
            finally:
                doc.close()
        if output_path.exists() and output_path.stat().st_size > 0:
            url = _visual_url_for_local_asset(output_path.resolve())
            return {
                "image_url": url,
                "page_image_url": url,
                "visual_url": url,
                "asset_path": output_path.resolve().as_posix(),
                "local_asset_path": output_path.resolve().as_posix(),
                "visual_asset_kind": "pdf_page_image",
                "visual_source": str(source),
                "visual_page": page_num,
                "visual_rendered_on_demand": True,
                "visual_pdf_source_path": pdf_path.as_posix(),
            }
    except Exception as e:
        logger.warning(f"On-demand PDF page render failed for {source} page {page_num}: {e}")
    return {}


def _local_page_image_metadata(source: Any, page: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
    if source is None or source == "" or page is None or page == "":
        return {}
    if not _is_pdf_result(source, metadata):
        return {}
    try:
        page_num = int(str(page).strip())
    except (TypeError, ValueError):
        return {}

    safe_stem = _safe_asset_stem(source)
    filename = f"page_{page_num:04d}.png"
    export_root = Path(os.getenv("VISUAL_EXPORT_ROOT") or (Path.cwd() / "data" / "visual"))
    candidates = [
        export_root / "pdf_pages" / safe_stem / filename,
    ]
    for root in _visual_asset_roots:
        candidates.append(root / "pdf_pages" / safe_stem / filename)
        candidates.append(root / "visual" / "pdf_pages" / safe_stem / filename)

    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if not resolved.exists() or resolved.stat().st_size <= 0:
            continue
        url = _visual_url_for_local_asset(resolved)
        return {
            "image_url": url,
            "page_image_url": url,
            "visual_url": url,
            "asset_path": resolved.as_posix(),
            "local_asset_path": resolved.as_posix(),
            "visual_asset_kind": "pdf_page_image",
            "visual_source": str(source),
            "visual_page": page_num,
        }
    return _render_missing_pdf_page_image_metadata(source, page_num, metadata)


def _source_page_visual_url(source: Any, page: Any, metadata: Dict[str, Any]) -> Optional[str]:
    if os.getenv("MAGELLANO_RAG_SYNTHETIC_SOURCE_PAGE_VISUALS", "false").lower() not in {"1", "true", "yes"}:
        return None
    if source is None or source == "" or page is None or page == "":
        return None
    if not _is_pdf_result(source, metadata):
        return None
    return (
        f"{_magellano_visual_base_url()}/visual/rag"
        f"?source={quote(str(source), safe='')}&page={quote(str(page), safe='')}"
    )


def _enrich_source_page_visuals(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched = []
    for result in results:
        item = dict(result)
        metadata = dict(item.get("metadata") or {})
        source = (
            _metadata_value(metadata, "source", "filename", "source_id")
            or item.get("source")
            or item.get("id")
        )
        page = _metadata_value(metadata, "page", "pages")
        local_visual_metadata = _local_page_image_metadata(source, page, metadata)
        for key, value in local_visual_metadata.items():
            metadata.setdefault(key, value)
            item.setdefault(key, value)
        item["metadata"] = metadata
        enriched.append(item)
    return enriched


def _similarity_value(result: Dict[str, Any]) -> Optional[float]:
    for key in ("similarity", "score"):
        value = result.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    distance = result.get("distance")
    if distance is not None:
        try:
            return max(0.0, min(1.0, 1.0 - float(distance)))
        except (TypeError, ValueError):
            return None
    return None


def _source_label(result: Dict[str, Any], idx: Optional[int] = None) -> str:
    metadata = result.get("metadata") or {}
    source = (
        _metadata_value(metadata, "source", "filename", "source_id")
        or result.get("source")
        or result.get("id")
        or (f"chunk_{idx}" if idx is not None else "sorgente sconosciuta")
    )
    parts = [str(source)]
    page = _metadata_value(metadata, "page", "pages")
    section = _metadata_value(metadata, "section", "title", "heading")
    row_start = _metadata_value(metadata, "row_range_start")
    row_end = _metadata_value(metadata, "row_range_end")
    group_by = _metadata_value(metadata, "group_by")
    group_value = _metadata_value(metadata, "group_value")

    if page is not None:
        parts.append(f"pag. {page}")
    if section:
        parts.append(f"sezione {section}")
    if row_start is not None or row_end is not None:
        start = row_start if row_start is not None else "?"
        end = row_end if row_end is not None else "?"
        parts.append(f"righe {start}-{end}")
    if group_by:
        parts.append(f"{group_by}: {group_value}")
    return ", ".join(parts)


def _public_chunk_refs(results: List[Dict[str, Any]], include_preview: bool = True) -> List[Dict[str, Any]]:
    refs = []
    for idx, result in enumerate(results, start=1):
        metadata = result.get("metadata") or {}
        similarity = _similarity_value(result)
        content = normalize_extracted_text(result.get("content") or "", compact=False)
        source = (
            _metadata_value(metadata, "source", "filename", "source_id")
            or result.get("source")
            or result.get("id")
            or f"chunk_{idx}"
        )
        page = _metadata_value(metadata, "page", "pages")
        image_url = _metadata_value(metadata, "image_url")
        visual_url = _metadata_value(metadata, "visual_url")
        page_image_url = _metadata_value(metadata, "page_image_url")
        local_visual_metadata = _local_page_image_metadata(source, page, metadata)
        ref = {
            "index": idx,
            "id": result.get("id") or metadata.get("chunk_id") or metadata.get("id"),
            "source": source,
            "page": page,
            "section": _metadata_value(metadata, "section", "title", "heading"),
            "type": _metadata_value(metadata, "type", "content_type", "mime_type"),
            "row_range_start": _metadata_value(metadata, "row_range_start"),
            "row_range_end": _metadata_value(metadata, "row_range_end"),
            "group_by": _metadata_value(metadata, "group_by"),
            "group_value": _metadata_value(metadata, "group_value"),
            "structured_kind": _metadata_value(metadata, "structured_kind"),
            "table_title": _metadata_value(metadata, "table_title"),
            "table_row_count": _metadata_value(metadata, "table_row_count"),
            "columns": _metadata_value(metadata, "columns", "table_columns"),
            "formula": _metadata_value(metadata, "formula", "equation"),
            "formula_count": _metadata_value(metadata, "formula_count"),
            "formula_latex": _metadata_value(metadata, "formula_latex"),
            "image_url": image_url or local_visual_metadata.get("image_url"),
            "page_image_url": page_image_url or local_visual_metadata.get("page_image_url"),
            "visual_url": visual_url or local_visual_metadata.get("visual_url"),
            "asset_path": _metadata_value(metadata, "asset_path") or local_visual_metadata.get("asset_path"),
            "similarity": round(similarity, 4) if similarity is not None else None,
            "label": _source_label(result, idx),
        }
        if include_preview:
            ref["preview"] = " ".join(content.split())[:260]
        refs.append({key: value for key, value in ref.items() if value is not None})
    return refs


def _result_sources(results: List[Dict[str, Any]]) -> List[str]:
    sources = []
    for idx, result in enumerate(results, start=1):
        source = _source_label(result, idx)
        if source and source not in sources:
            sources.append(source)
    return sources


def _base_document_type(value: Any) -> str:
    doc_type = str(value or "unknown")
    if doc_type.startswith("pdf"):
        return "pdf"
    return doc_type


def _invalidate_vector_document_count_cache() -> None:
    vector_document_count_cache.clear()


def _add_chunks_batch(chunks: List[Dict[str, Any]], batch_size: int) -> Dict[str, Any]:
    if vector_store is None:
        raise RuntimeError("Vector store not initialized")
    result = vector_store.add_chunks_batch(chunks, batch_size=batch_size)
    _invalidate_vector_document_count_cache()
    return result


def _vector_document_count(document_type: Optional[str] = None, batch_size: int = 1000) -> int:
    if not vector_store or not getattr(vector_store, "collection", None):
        return 0
    cache_key = document_type or "*"
    if VECTOR_STATS_CACHE_TTL_SECONDS > 0:
        cached = vector_document_count_cache.get(cache_key)
        if cached and cached.get("expires_at", datetime.min) > datetime.utcnow():
            return int(cached.get("value") or 0)

    try:
        total_chunks = int(vector_store.collection.count())
    except Exception:
        return 0

    sources = set()
    for batch_offset in range(0, total_chunks, batch_size):
        try:
            batch = vector_store.collection.get(
                limit=min(batch_size, total_chunks - batch_offset),
                offset=batch_offset,
                include=["metadatas"],
            )
        except Exception as e:
            logger.warning(f"Unable to scan vector document metadata: {e}")
            break
        for idx, metadata in enumerate(batch.get("metadatas") or []):
            metadata = metadata or {}
            base_type = _base_document_type(_metadata_value(metadata, "type", "content_type", "mime_type"))
            if document_type and base_type != document_type and metadata.get("type") != document_type:
                continue
            source = (
                _metadata_value(metadata, "source", "filename", "source_id")
                or (batch.get("ids") or [None])[idx]
            )
            if source:
                sources.add(str(source))
    count = len(sources)
    if VECTOR_STATS_CACHE_TTL_SECONDS > 0:
        vector_document_count_cache[cache_key] = {
            "value": count,
            "expires_at": datetime.utcnow() + timedelta(seconds=VECTOR_STATS_CACHE_TTL_SECONDS),
        }
    return count


def _vector_document_summaries(
    limit: int = 50,
    offset: int = 0,
    document_type: Optional[str] = None,
    batch_size: int = 1000,
) -> Dict[str, Any]:
    if not vector_store or not getattr(vector_store, "collection", None):
        return {"documents": [], "total_documents": 0, "total_chunks": 0}

    try:
        total_chunks = int(vector_store.collection.count())
    except Exception as e:
        logger.warning(f"Unable to count vector documents: {e}")
        return {"documents": [], "total_documents": 0, "total_chunks": 0}

    grouped: Dict[str, Dict[str, Any]] = {}
    for batch_offset in range(0, total_chunks, batch_size):
        try:
            batch = vector_store.collection.get(
                limit=min(batch_size, total_chunks - batch_offset),
                offset=batch_offset,
                include=["metadatas", "documents"],
            )
        except Exception as e:
            logger.warning(f"Unable to list vector documents: {e}")
            break

        ids = batch.get("ids") or []
        documents = batch.get("documents") or []
        metadatas = batch.get("metadatas") or []
        for idx, metadata in enumerate(metadatas):
            metadata = metadata or {}
            raw_type = _metadata_value(metadata, "type", "content_type", "mime_type")
            base_type = _base_document_type(raw_type)
            if document_type and base_type != document_type and raw_type != document_type:
                continue

            source = (
                _metadata_value(metadata, "source", "filename", "source_id")
                or (ids[idx] if idx < len(ids) else None)
                or f"document_{idx + batch_offset}"
            )
            source = str(source)
            entry = grouped.setdefault(
                source,
                {
                    "source_id": source,
                    "source": source,
                    "type": base_type,
                    "types": set(),
                    "chunks": 0,
                    "pages": set(),
                    "visual_assets": set(),
                    "table_chunks": 0,
                    "formula_chunks": 0,
                    "first_seen": None,
                    "last_seen": None,
                    "preview": "",
                },
            )
            entry["chunks"] += 1
            entry["types"].add(str(raw_type or base_type))
            page = _metadata_value(metadata, "page", "pages")
            if page is not None:
                entry["pages"].add(str(page))
            visual = _metadata_value(metadata, "page_image_url", "image_url", "visual_url", "asset_path")
            if visual:
                entry["visual_assets"].add(str(visual))
            if metadata.get("structured_kind") == "table" or raw_type == "pdf_table":
                entry["table_chunks"] += 1
            if metadata.get("formula_count") or metadata.get("formula_latex"):
                entry["formula_chunks"] += 1
            timestamp = _metadata_value(metadata, "timestamp", "created_at", "ingested_at")
            if timestamp:
                timestamp = str(timestamp)
                entry["first_seen"] = min(entry["first_seen"], timestamp) if entry["first_seen"] else timestamp
                entry["last_seen"] = max(entry["last_seen"], timestamp) if entry["last_seen"] else timestamp
            if not entry["preview"] and idx < len(documents) and documents[idx]:
                entry["preview"] = " ".join(
                    normalize_extracted_text(documents[idx], compact=False).split()
                )[:220]

    docs = []
    for entry in grouped.values():
        pages = sorted(
            entry.pop("pages"),
            key=lambda value: (0, int(value)) if str(value).isdigit() else (1, str(value)),
        )
        visual_assets = entry.pop("visual_assets")
        entry["types"] = sorted(entry["types"])
        entry["pages"] = len(pages)
        if pages:
            entry["page_range"] = f"{pages[0]}-{pages[-1]}" if len(pages) > 1 else pages[0]
        entry["visual_assets"] = len(visual_assets)
        docs.append(entry)

    docs.sort(key=lambda item: (item.get("last_seen") or "", item.get("source") or ""), reverse=True)
    return {
        "documents": docs[offset : offset + limit],
        "total_documents": len(docs),
        "total_chunks": total_chunks,
    }


def _retrieval_fallback_answer(results: List[Dict[str, Any]]) -> str:
    if not results:
        return "Nessun documento rilevante trovato."

    lines = []
    for idx, result in enumerate(results[:5], start=1):
        source = _source_label(result, idx)
        similarity = _similarity_value(result)
        content = normalize_extracted_text(result.get("content") or "", compact=False)[:450]
        score = f" (similarita {similarity:.2f})" if similarity is not None else ""
        lines.append(f"[{idx}] {source}{score}\n{content}")
    return "Magellano non disponibile. Risultati retrieval MiniLM:\n\n" + "\n\n".join(lines)


_RAG_RETRIEVAL_NOISE_TERMS = {
    "visualizza",
    "mostra",
    "vedi",
    "vedere",
    "trova",
    "cerca",
    "descrivi",
    "descrive",
    "descrivere",
    "spiega",
    "spiegami",
    "riassumi",
    "riassumimi",
    "parlami",
    "analizza",
    "illustra",
    "definisci",
    "cos",
    "cosa",
    "come",
    "dammi",
    "fammi",
    "apri",
    "renderizza",
    "visualizzare",
    "mostrare",
    "tabella",
    "tabelle",
    "grafico",
    "grafici",
    "immagine",
    "immagini",
    "figura",
    "figure",
    "visual",
    "visuale",
    "asset",
    "formula",
    "formule",
    "equazione",
    "equazioni",
    "funzione",
    "funzioni",
    "function",
    "functions",
    "la",
    "il",
    "lo",
    "le",
    "gli",
    "i",
    "un",
    "una",
    "uno",
    "del",
    "della",
    "delle",
    "dei",
    "degli",
    "di",
    "da",
    "dal",
    "dallo",
    "dalla",
    "dai",
    "dagli",
    "con",
    "per",
    "su",
    "nel",
    "nella",
    "nelle",
    "nei",
    "of",
    "the",
    "show",
    "find",
    "display",
    "image",
    "table",
    "figure",
    "chart",
}


def _env_int(name: str, default: int, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


PDF_INGEST_ENABLED = os.getenv("PDF_INGEST_ENABLED", "true").lower() in {"1", "true", "yes", "on", "si"}
PDF_URL_INGEST_MODE = os.getenv("PDF_URL_INGEST_MODE", "deferred").strip().lower()
PDF_INGEST_QUEUE_MAX_SIZE = _env_int("PDF_INGEST_QUEUE_MAX_SIZE", 30, minimum=1, maximum=500)
PDF_INGEST_WORKERS = _env_int("PDF_INGEST_WORKERS", 1, minimum=1, maximum=4)
PDF_INGEST_BATCH_SIZE = _env_int("PDF_INGEST_BATCH_SIZE", 16, minimum=1, maximum=CONFIG["MAX_BATCH_SIZE"])
PDF_INGEST_COOLDOWN_SECONDS = _env_int("PDF_INGEST_COOLDOWN_SECONDS", 3, minimum=0, maximum=60)
PDF_INGEST_JOB_HISTORY_LIMIT = _env_int("PDF_INGEST_JOB_HISTORY_LIMIT", 200, minimum=20, maximum=2000)
VECTOR_STATS_CACHE_TTL_SECONDS = _env_int("VECTOR_STATS_CACHE_TTL_SECONDS", 30, minimum=0, maximum=300)
PDF_INGEST_STATE_PATH = Path(os.getenv("PDF_INGEST_STATE_PATH", "data/pdf_ingest_jobs.json"))
VECTOR_STATS_DEEP_DOCUMENT_COUNT = os.getenv("VECTOR_STATS_DEEP_DOCUMENT_COUNT", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
    "si",
}
RAG_MAX_RETRIEVAL_CHUNKS = _env_int("RAG_MAX_RETRIEVAL_CHUNKS", 120, minimum=5, maximum=240)
RAG_DEFAULT_RETRIEVAL_CHUNKS = _env_int("RAG_DEFAULT_RETRIEVAL_CHUNKS", 48, minimum=1, maximum=RAG_MAX_RETRIEVAL_CHUNKS)
RAG_GENERATION_CONTEXT_CHUNKS = _env_int("RAG_GENERATION_CONTEXT_CHUNKS", 96, minimum=4, maximum=RAG_MAX_RETRIEVAL_CHUNKS)
RAG_MAX_TOKENS = _env_int("RAG_MAX_TOKENS", 49152, minimum=512, maximum=65536)
RAG_DEFAULT_MAX_TOKENS = _env_int("RAG_DEFAULT_MAX_TOKENS", 12288, minimum=128, maximum=RAG_MAX_TOKENS)
RAG_MAX_TEMPERATURE = float(os.getenv("RAG_MAX_TEMPERATURE", "1.8"))


_RAG_GENERIC_ANCHOR_TERMS = {
    "metodo",
    "metodi",
    "model",
    "models",
    "modello",
    "modelli",
    "teoria",
    "theory",
    "sistema",
    "sistemi",
    "system",
    "systems",
    "architettura",
    "architecture",
    "struttura",
    "structure",
    "parametro",
    "parametri",
    "parameter",
    "parameters",
    "dato",
    "dati",
    "data",
    "valore",
    "valori",
    "value",
    "values",
    "pagina",
    "page",
    "documento",
    "document",
    "pdf",
}


def _rag_env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


_RAG_ANCHORLESS_LOW_CONFIDENCE = _rag_env_float("RAG_ANCHORLESS_LOW_CONFIDENCE", 0.45)
_RAG_ANCHORED_KEEP_MARGIN = _rag_env_float("RAG_ANCHORED_KEEP_MARGIN", 0.08)


def _rag_unique_terms(terms: List[str]) -> List[str]:
    seen = set()
    unique = []
    for term in terms:
        term = str(term or "").strip().lower()
        if not term or term in seen:
            continue
        seen.add(term)
        unique.append(term)
    return unique


def _rag_domain_expansion_terms(raw_query: str, base_terms: List[str]) -> List[str]:
    words = set(base_terms) | set(_rag_query_terms(raw_query))
    expansions: List[str] = []
    if {"kolmogorov", "arnold"}.issubset(words):
        # KAN documents often spell the concept as network/theorem, not as a bare formula.
        expansions.extend(["network", "networks", "kan", "mlp"])
    if "perceptron" in words and ({"multi", "layer"} & words or "multilayer" in words):
        expansions.extend(["mlp", "multi-layer", "multilayer"])
    return expansions


def _rag_retrieval_query(query: str) -> str:
    """Remove UI intent words before MiniLM retrieval, keeping the original query for Magellano."""
    raw = normalize_extracted_text(query or "", compact=True)
    if not raw:
        return raw
    normalized = re.sub(r"[^\wÀ-ÿ]+", " ", raw.lower(), flags=re.UNICODE)
    terms = [
        term
        for term in normalized.split()
        if len(term) > 1 and term not in _RAG_RETRIEVAL_NOISE_TERMS
    ]
    terms = _rag_unique_terms(terms + _rag_domain_expansion_terms(raw, terms))
    cleaned = " ".join(terms).strip()
    return cleaned or raw


def _rag_query_terms(query: str) -> List[str]:
    return [
        term
        for term in re.findall(r"[\wÀ-ÿ]+", (query or "").lower(), flags=re.UNICODE)
        if (
            (len(term) > 2 or (len(term) > 1 and any(char.isdigit() for char in term)))
            and term not in _RAG_RETRIEVAL_NOISE_TERMS
        )
    ]


def _rag_anchor_terms(query: str, retrieval_query: str) -> List[str]:
    """Terms that must remain grounded for narrow technical/user-intent queries."""
    raw_terms = _rag_query_terms(query)
    terms = raw_terms or _rag_query_terms(retrieval_query)
    anchors = [
        term
        for term in terms
        if term not in _RAG_GENERIC_ANCHOR_TERMS
    ]
    return _rag_unique_terms(anchors)


def _rag_required_lexical_groups(query: str, retrieval_query: str) -> List[tuple]:
    anchors = [(term,) for term in _rag_anchor_terms(query, retrieval_query)]
    lowered = f" {normalize_extracted_text(query or '', compact=True).lower()} "
    words = set(_rag_query_terms(f"{query} {retrieval_query}"))
    if "perceptron" in words and ({"multi", "layer"} & words or "multilayer" in words):
        anchors = [
            group for group in anchors
            if not set(group).issubset({"multi", "layer", "perceptron", "multilayer"})
        ]
        anchors.append((
            "multi layer perceptron",
            "multi-layer perceptron",
            "multilayer perceptron",
            "mlp",
            "mule-layer perceptron",
        ))
    if re.search(r"\b(funzione|funzioni|function|functions)\b", lowered, flags=re.IGNORECASE):
        anchors.append(("funzione", "funzioni", "function", "functions"))
    return anchors


def _rag_result_haystack(result: Dict[str, Any]) -> str:
    metadata = result.get("metadata") or {}
    text = " ".join([
        str(result.get("content") or ""),
        str(result.get("source") or ""),
        str(result.get("id") or ""),
        str(_metadata_value(metadata, "source", "filename", "source_id") or ""),
        str(_metadata_value(metadata, "section", "title", "heading") or ""),
        str(_metadata_value(metadata, "table_title") or ""),
        str(_metadata_value(metadata, "structured_kind") or ""),
    ])
    normalized = normalize_extracted_text(text, compact=True).lower()
    ocr_joined = normalized
    for _ in range(3):
        ocr_joined = re.sub(r"\b([^\W\d_])\s+([^\W\d_]{2,})\b", r"\1\2", ocr_joined, flags=re.UNICODE)
        ocr_joined = re.sub(r"\b([^\W\d_]{3,})\s+([^\W\d_]{1,2})\b", r"\1\2", ocr_joined, flags=re.UNICODE)
    if ocr_joined != normalized:
        return f"{normalized} {ocr_joined}"
    return normalized


def _rag_lexical_hits(result: Dict[str, Any], terms: List[str]) -> int:
    if not terms:
        return 0
    haystack = _rag_result_haystack(result)
    return sum(1 for term in terms if term in haystack)


def _rag_required_group_hits(result: Dict[str, Any], groups: List[tuple]) -> int:
    if not groups:
        return 0
    haystack = _rag_result_haystack(result)
    return sum(
        1
        for group in groups
        if any(term in haystack for term in group)
    )


def _rag_filter_coherent_results(
    query: str,
    retrieval_query: str,
    results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Prefer precision over plausible-but-wrong RAG context for named/technical anchors."""
    if not results:
        return []

    anchors = _rag_anchor_terms(query, retrieval_query)
    if not anchors:
        return results
    required_groups = _rag_required_lexical_groups(query, retrieval_query)

    similarities = [
        _similarity_value(result)
        for result in results
        if _similarity_value(result) is not None
    ]
    max_similarity = max(similarities) if similarities else 0.0

    anchored = [
        result
        for result in results
        if _rag_required_group_hits(result, required_groups) == len(required_groups)
    ]

    if anchored:
        best_anchored_similarity = max(
            (_similarity_value(result) or 0.0)
            for result in anchored
        )
        strong_semantic_floor = max(
            _RAG_ANCHORLESS_LOW_CONFIDENCE,
            best_anchored_similarity + _RAG_ANCHORED_KEEP_MARGIN,
        )
        coherent = [
            result
            for result in results
            if (
                _rag_required_group_hits(result, required_groups) == len(required_groups)
                or (_similarity_value(result) or 0.0) >= strong_semantic_floor
            )
        ]
        return coherent or anchored

    if len(required_groups) >= 2:
        logger.info(
            "RAG coherence guard blocked multi-anchor results without lexical grounding "
            "query=%r retrieval_query=%r anchors=%s max_similarity=%.4f",
            query,
            retrieval_query,
            anchors,
            max_similarity,
        )
        return []

    if max_similarity < _RAG_ANCHORLESS_LOW_CONFIDENCE:
        logger.info(
            "RAG coherence guard blocked anchorless low-confidence results "
            "query=%r retrieval_query=%r anchors=%s max_similarity=%.4f",
            query,
            retrieval_query,
            anchors,
            max_similarity,
        )
        return []

    return results


def _rag_no_relevant_answer(query: str, retrieval_query: str) -> str:
    anchors = _rag_anchor_terms(query, retrieval_query)
    if anchors:
        return (
            "Nessun documento rilevante trovato nel RAG per i termini chiave: "
            f"{', '.join(anchors)}. Ho scartato candidati a bassa coerenza "
            "per evitare una risposta basata su fonti non pertinenti."
        )
    return "Nessun documento rilevante trovato."


def _rag_has_kolmogorov_arnold_intent(query: str, retrieval_query: str) -> bool:
    words = set(_rag_query_terms(f"{query} {retrieval_query}"))
    return {"kolmogorov", "arnold"}.issubset(words)


def _rag_result_has_visual(result: Dict[str, Any]) -> bool:
    metadata = result.get("metadata") or {}
    return any(
        _metadata_value(metadata, key) or result.get(key)
        for key in ("image_url", "page_image_url", "visual_url", "asset_path", "local_asset_path")
    )


def _rank_rag_results(
    query: str,
    retrieval_query: str,
    results: List[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    if not results:
        return []

    terms = _rag_query_terms(retrieval_query or query)
    kolmogorov_arnold = _rag_has_kolmogorov_arnold_intent(query, retrieval_query)
    ka_terms = ("kolmogorov", "arnold", "kan", "network", "networks", "mlp")
    scored = []

    for index, result in enumerate(results, start=1):
        similarity = _similarity_value(result) or 0.0
        haystack = _rag_result_haystack(result)
        hits = _rag_lexical_hits(result, terms)
        score = similarity + (0.045 * hits) - (0.002 * max(index - 1, 0))

        if kolmogorov_arnold:
            ka_hits = sum(1 for term in ka_terms if term in haystack)
            score += 0.09 * ka_hits
            if "kolmogorov" in haystack and "arnold" in haystack:
                score += 0.20
            if "kan" in haystack and ("mlp" in haystack or "network" in haystack):
                score += 0.12
            if "mlp_vs_kan" in haystack or "mlp vs kan" in haystack:
                score += 0.15
            if _rag_result_has_visual(result):
                score += 0.03
            if ka_hits == 0:
                score -= 0.15

        scored.append((score, -index, result))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scored[:limit]]


def _rag_candidate_count(limit: int) -> int:
    return min(240, max(limit, limit * 3, 120))


def _select_generation_context(
    query: str,
    retrieval_query: str,
    results: List[Dict[str, Any]],
    max_chunks: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not results:
        return []
    if max_chunks is None:
        max_chunks = RAG_GENERATION_CONTEXT_CHUNKS
    max_chunks = max(1, min(int(max_chunks), len(results)))
    terms = _rag_query_terms(retrieval_query or query)
    similarities = [
        _similarity_value(result)
        for result in results
        if _similarity_value(result) is not None
    ]
    max_similarity = max(similarities) if similarities else None
    similarity_floor = max(0.0, max_similarity - 0.10) if max_similarity is not None else None

    scored = []
    for index, result in enumerate(results, start=1):
        similarity = _similarity_value(result) or 0.0
        hits = _rag_lexical_hits(result, terms)
        all_terms_hit = bool(terms) and hits == len(set(terms))
        score = similarity + (0.08 * hits) + (0.06 if all_terms_hit else 0.0)
        score -= 0.015 * max(index - 1, 0)
        keep = (
            index <= 5
            or hits > 0
            or (similarity_floor is not None and similarity >= similarity_floor)
        )
        if keep:
            scored.append((score, index, result))

    if not scored:
        return results[:max_chunks]

    scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    selected = [item[2] for item in scored[:max_chunks]]
    return selected or results[:max_chunks]


async def _optional_json(request: Request) -> Dict[str, Any]:
    """Read JSON only for JSON requests; form routes keep working unchanged."""
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type.lower():
        return {}
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {e}")
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")
    return payload


def _payload_value(payload: Dict[str, Any], key: str, current: Any) -> Any:
    return payload[key] if key in payload and payload[key] is not None else current


def _as_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field} must be an integer")
    if number < minimum or number > maximum:
        raise HTTPException(status_code=400, detail=f"{field} must be between {minimum} and {maximum}")
    return number


def _as_float(value: Any, field: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field} must be a number")
    if number < minimum or number > maximum:
        raise HTTPException(status_code=400, detail=f"{field} must be between {minimum} and {maximum}")
    return number


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "si"}


def _is_private_download_host(hostname: str) -> bool:
    if not hostname:
        return True
    if hostname.lower() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    for family, _, _, _, sockaddr in addresses:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            return True
    return False


async def _download_pdf_from_url(pdf_url: str, max_bytes: int) -> bytes:
    parsed = urlparse(pdf_url)
    if parsed.scheme not in {"https", "http"}:
        raise HTTPException(status_code=400, detail="pdf_url must be http or https")
    if parsed.scheme == "http" and os.getenv("ALLOW_HTTP_PDF_URLS", "false").lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=400, detail="Only https pdf_url is allowed by default")
    if (
        os.getenv("ALLOW_PRIVATE_PDF_URLS", "false").lower() not in {"1", "true", "yes"}
        and _is_private_download_host(parsed.hostname or "")
    ):
        raise HTTPException(status_code=400, detail="Private/local pdf_url hosts are not allowed")

    import httpx

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(90.0),
            follow_redirects=True,
            trust_env=False,
        ) as client:
            async with client.stream("GET", pdf_url) as response:
                response.raise_for_status()
                chunks = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise HTTPException(status_code=413, detail="Downloaded PDF exceeds max file size")
                    chunks.append(chunk)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"PDF download failed: {e}")

    content = b"".join(chunks)
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Downloaded URL did not return a PDF")
    return content


def _filename_from_pdf_url(pdf_url: str, source_id: Optional[str] = None) -> str:
    path_name = Path(unquote(urlparse(pdf_url).path)).name
    filename = path_name if path_name.lower().endswith(".pdf") else ""
    if not filename and source_id:
        filename = f"{source_id}.pdf"
    if not filename:
        filename = f"remote_pdf_{uuid.uuid4().hex[:8]}.pdf"
    return re.sub(r'[<>:"/\\|?*]+', "_", filename)


def _pdf_ingest_job_id(pdf_url: str, source_id: Optional[str], filename: Optional[str]) -> str:
    raw = "|".join([pdf_url or "", source_id or "", filename or ""])
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:20]


def _pdf_ingest_public_job(job: Dict[str, Any]) -> Dict[str, Any]:
    public_keys = {
        "job_id",
        "status",
        "pdf_url",
        "source_id",
        "filename",
        "created_at",
        "queued_at",
        "started_at",
        "finished_at",
        "worker",
        "attempts",
        "queue_position",
        "error",
        "result",
        "duplicate",
    }
    return {key: value for key, value in job.items() if key in public_keys and value is not None}


def _pdf_ingest_summary() -> Dict[str, Any]:
    statuses: Dict[str, int] = {}
    for job in pdf_ingest_jobs.values():
        status = str(job.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "enabled": PDF_INGEST_ENABLED,
        "mode": PDF_URL_INGEST_MODE,
        "workers": PDF_INGEST_WORKERS,
        "queue_max_size": PDF_INGEST_QUEUE_MAX_SIZE,
        "queue_depth": pdf_ingest_queue.qsize() if pdf_ingest_queue else 0,
        "jobs_tracked": len(pdf_ingest_jobs),
        "statuses": statuses,
        "state_path": PDF_INGEST_STATE_PATH.as_posix(),
    }


def _persist_pdf_ingest_state() -> None:
    try:
        PDF_INGEST_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        jobs = sorted(
            pdf_ingest_jobs.values(),
            key=lambda job: str(job.get("created_at") or ""),
            reverse=True,
        )[:PDF_INGEST_JOB_HISTORY_LIMIT]
        payload = {
            "version": 1,
            "updated_at": datetime.utcnow().isoformat(),
            "jobs": jobs,
        }
        tmp_path = PDF_INGEST_STATE_PATH.with_suffix(PDF_INGEST_STATE_PATH.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(PDF_INGEST_STATE_PATH)
    except Exception as e:
        logger.warning(f"Unable to persist PDF ingest state: {e}")


def _load_pdf_ingest_state() -> None:
    global pdf_ingest_state_loaded
    if pdf_ingest_state_loaded:
        return
    pdf_ingest_state_loaded = True
    if not PDF_INGEST_STATE_PATH.exists():
        return
    try:
        payload = json.loads(PDF_INGEST_STATE_PATH.read_text(encoding="utf-8"))
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        for raw_job in jobs:
            if not isinstance(raw_job, dict) or not raw_job.get("job_id"):
                continue
            job = dict(raw_job)
            if job.get("status") in {"queued", "running"}:
                job["status"] = "queued"
                job.pop("worker", None)
                job["recovered_at"] = datetime.utcnow().isoformat()
            pdf_ingest_jobs[job["job_id"]] = job
        logger.info("Loaded %s deferred PDF ingest jobs from %s", len(pdf_ingest_jobs), PDF_INGEST_STATE_PATH)
    except Exception as e:
        logger.warning(f"Unable to load PDF ingest state: {e}")


async def _requeue_pending_pdf_ingest_jobs() -> None:
    if pdf_ingest_queue is None:
        return
    queued_ids = set(getattr(pdf_ingest_queue, "_queue", []))
    for job_id, job in list(pdf_ingest_jobs.items()):
        if job.get("status") != "queued" or job_id in queued_ids:
            continue
        try:
            pdf_ingest_queue.put_nowait(job_id)
        except asyncio.QueueFull:
            logger.warning("Deferred PDF ingest queue full while recovering jobs")
            break


async def _ensure_pdf_ingest_runtime() -> None:
    global pdf_ingest_queue, pdf_ingest_lock
    if pdf_ingest_queue is None:
        pdf_ingest_queue = asyncio.Queue(maxsize=PDF_INGEST_QUEUE_MAX_SIZE)
    if pdf_ingest_lock is None:
        pdf_ingest_lock = asyncio.Lock()
    _load_pdf_ingest_state()
    await _requeue_pending_pdf_ingest_jobs()
    if PDF_INGEST_ENABLED and not pdf_ingest_workers:
        await _start_pdf_ingest_workers()


async def _start_pdf_ingest_workers() -> None:
    global pdf_ingest_queue, pdf_ingest_lock
    if not PDF_INGEST_ENABLED:
        logger.info("Deferred PDF ingestion disabled by PDF_INGEST_ENABLED=false")
        return
    if pdf_ingest_queue is None:
        pdf_ingest_queue = asyncio.Queue(maxsize=PDF_INGEST_QUEUE_MAX_SIZE)
    if pdf_ingest_lock is None:
        pdf_ingest_lock = asyncio.Lock()
    while len(pdf_ingest_workers) < PDF_INGEST_WORKERS:
        worker_idx = len(pdf_ingest_workers) + 1
        task = asyncio.create_task(_pdf_ingest_worker(worker_idx), name=f"pdf-ingest-worker-{worker_idx}")
        pdf_ingest_workers.append(task)
    logger.info(
        "Deferred PDF ingestion ready: workers=%s queue_max=%s batch_size=%s",
        len(pdf_ingest_workers),
        PDF_INGEST_QUEUE_MAX_SIZE,
        PDF_INGEST_BATCH_SIZE,
    )


async def _stop_pdf_ingest_workers() -> None:
    if not pdf_ingest_workers:
        return
    for task in pdf_ingest_workers:
        task.cancel()
    await asyncio.gather(*pdf_ingest_workers, return_exceptions=True)
    pdf_ingest_workers.clear()


async def _enqueue_pdf_ingest_job(
    pdf_url: str,
    source_id: Optional[str],
    filename: Optional[str],
    chunk_size: int,
    chunk_overlap: int,
    batch_size: int,
    extract_page_images: bool,
    extract_tables: bool,
    extract_formulas: bool,
) -> Dict[str, Any]:
    await _ensure_pdf_ingest_runtime()
    if not PDF_INGEST_ENABLED:
        return {
            "status": "disabled",
            "reason": "PDF_INGEST_ENABLED=false",
            "pdf_url": pdf_url,
            "source_id": source_id,
            "filename": filename,
        }
    if pdf_ingest_queue is None or pdf_ingest_lock is None:
        return {"status": "unavailable", "reason": "pdf ingest queue not initialized"}

    resolved_filename = filename or _filename_from_pdf_url(pdf_url, source_id)
    job_id = _pdf_ingest_job_id(pdf_url, source_id, resolved_filename)
    now = datetime.utcnow().isoformat()

    async with pdf_ingest_lock:
        existing = pdf_ingest_jobs.get(job_id)
        if existing and existing.get("status") in {"queued", "running", "success"}:
            duplicate = _pdf_ingest_public_job(existing)
            duplicate["duplicate"] = True
            if existing.get("status") == "queued":
                queued_ids = list(getattr(pdf_ingest_queue, "_queue", []))
                duplicate["queue_position"] = queued_ids.index(job_id) + 1 if job_id in queued_ids else None
            return duplicate

        if pdf_ingest_queue.full():
            return {
                "job_id": job_id,
                "status": "rejected",
                "reason": "queue_full",
                "queue_depth": pdf_ingest_queue.qsize(),
                "queue_max_size": PDF_INGEST_QUEUE_MAX_SIZE,
                "pdf_url": pdf_url,
                "source_id": source_id,
                "filename": resolved_filename,
            }

        job = {
            "job_id": job_id,
            "status": "queued",
            "pdf_url": pdf_url,
            "source_id": source_id,
            "filename": resolved_filename,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "batch_size": min(batch_size, PDF_INGEST_BATCH_SIZE),
            "extract_page_images": extract_page_images,
            "extract_tables": extract_tables,
            "extract_formulas": extract_formulas,
            "created_at": now,
            "queued_at": now,
            "attempts": int(existing.get("attempts", 0)) + 1 if existing else 1,
        }
        pdf_ingest_jobs[job_id] = job
        await pdf_ingest_queue.put(job_id)

        if len(pdf_ingest_jobs) > PDF_INGEST_JOB_HISTORY_LIMIT:
            removable = [
                key for key, value in pdf_ingest_jobs.items()
                if value.get("status") in {"success", "failed", "rejected"}
            ]
            for key in removable[: max(0, len(pdf_ingest_jobs) - PDF_INGEST_JOB_HISTORY_LIMIT)]:
                pdf_ingest_jobs.pop(key, None)

        _persist_pdf_ingest_state()
        public_job = _pdf_ingest_public_job(job)
        public_job["queue_position"] = pdf_ingest_queue.qsize()
        return public_job


def _process_pdf_bytes_to_vector(
    contents: bytes,
    resolved_filename: str,
    source_id: Optional[str],
    pdf_url: Optional[str],
    chunk_size: int,
    chunk_overlap: int,
    batch_size: int,
    extract_page_images: bool,
    extract_tables: bool,
    extract_formulas: bool,
) -> Dict[str, Any]:
    if embedder is None or vector_store is None:
        raise RuntimeError("Services not initialized")
    if DocumentProcessor is None:
        raise RuntimeError("Document processor not available")

    processor = DocumentProcessor(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = processor.process_pdf(
        contents,
        resolved_filename,
        extract_page_images=extract_page_images,
        extract_tables=extract_tables,
        extract_formulas=extract_formulas,
    )
    if not chunks:
        raise ValueError("No content could be extracted from PDF")

    for chunk in chunks:
        metadata = chunk.setdefault("metadata", {})
        if pdf_url:
            metadata["pdf_url"] = pdf_url
        if source_id:
            metadata["source_id"] = source_id
            metadata.setdefault("source", resolved_filename)

    _add_chunks_batch(chunks, batch_size=min(batch_size, len(chunks)))

    pages = len(set(c.get("metadata", {}).get("page", 0) for c in chunks))
    page_images = len({
        c.get("metadata", {}).get("local_asset_path")
        for c in chunks
        if c.get("metadata", {}).get("visual_asset_kind") == "pdf_page_image"
        and c.get("metadata", {}).get("local_asset_path")
    })
    table_chunks = sum(
        1 for c in chunks
        if c.get("metadata", {}).get("structured_kind") == "table"
        or c.get("metadata", {}).get("structured_kind") == "table_visual_fallback"
        or c.get("metadata", {}).get("type") == "pdf_table"
    )
    formula_chunks = sum(1 for c in chunks if c.get("metadata", {}).get("formula_count"))

    return {
        "filename": resolved_filename,
        "source_id": source_id,
        "pdf_url": pdf_url,
        "chunks_processed": len(chunks),
        "chunks_created": len(chunks),
        "pages": pages,
        "page_images": page_images,
        "table_chunks": table_chunks,
        "formula_chunks": formula_chunks,
        "file_size_bytes": len(contents),
    }


async def _run_pdf_ingest_job(job: Dict[str, Any], worker_idx: int) -> None:
    start_time = datetime.utcnow()
    job["status"] = "running"
    job["worker"] = worker_idx
    job["started_at"] = start_time.isoformat()
    _persist_pdf_ingest_state()
    contents = b""
    try:
        logger.info(
            "Deferred PDF ingest started: job=%s source=%s url=%s",
            job["job_id"],
            job.get("source_id") or job.get("filename"),
            job.get("pdf_url"),
        )
        max_size = CONFIG["MAX_FILE_SIZE_MB"] * 1024 * 1024
        contents = await _download_pdf_from_url(job["pdf_url"], max_size)
        result = await asyncio.to_thread(
            _process_pdf_bytes_to_vector,
            contents,
            job["filename"],
            job.get("source_id"),
            job.get("pdf_url"),
            int(job.get("chunk_size") or CONFIG["DEFAULT_CHUNK_SIZE"]),
            int(job.get("chunk_overlap") or CONFIG["DEFAULT_CHUNK_OVERLAP"]),
            int(job.get("batch_size") or PDF_INGEST_BATCH_SIZE),
            bool(job.get("extract_page_images", True)),
            bool(job.get("extract_tables", True)),
            bool(job.get("extract_formulas", True)),
        )
        result["processing_time_ms"] = round((datetime.utcnow() - start_time).total_seconds() * 1000, 2)
        job["status"] = "success"
        job["finished_at"] = datetime.utcnow().isoformat()
        job["result"] = result
        _persist_pdf_ingest_state()
        processed_files.append({
            "type": "pdf",
            "ingest_mode": "deferred",
            "timestamp": job["finished_at"],
            **result,
        })
        logger.info(
            "Deferred PDF ingest completed: job=%s chunks=%s pages=%s visuals=%s",
            job["job_id"],
            result.get("chunks_processed"),
            result.get("pages"),
            result.get("page_images"),
        )
    except asyncio.CancelledError:
        job["status"] = "cancelled"
        job["finished_at"] = datetime.utcnow().isoformat()
        _persist_pdf_ingest_state()
        raise
    except Exception as e:
        error = str(getattr(e, "detail", None) or e)
        job["status"] = "failed"
        job["finished_at"] = datetime.utcnow().isoformat()
        job["error"] = error
        _persist_pdf_ingest_state()
        logger.error("Deferred PDF ingest failed: job=%s error=%s", job.get("job_id"), error)
        if dlq:
            dlq.add_failed_file(
                filename=job.get("filename") or "remote.pdf",
                error=error,
                reason="PARSING_ERROR",
                file_size_bytes=len(contents),
                metadata={
                    "filename": job.get("filename"),
                    "pdf_url": job.get("pdf_url"),
                    "source_id": job.get("source_id"),
                    "content_type": "pdf_url",
                    "ingest_mode": "deferred",
                    "job_id": job.get("job_id"),
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
    finally:
        if PDF_INGEST_COOLDOWN_SECONDS:
            await asyncio.sleep(PDF_INGEST_COOLDOWN_SECONDS)


async def _pdf_ingest_worker(worker_idx: int) -> None:
    assert pdf_ingest_queue is not None
    while True:
        job_id = await pdf_ingest_queue.get()
        try:
            job = pdf_ingest_jobs.get(job_id)
            if job:
                await _run_pdf_ingest_job(job, worker_idx)
        finally:
            pdf_ingest_queue.task_done()


# ====================== FRONTEND ENDPOINTS ======================
@app.get("/", response_class=HTMLResponse, tags=["Frontend"])
async def serve_frontend():
    """Serve la dashboard frontend"""
    try:
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        
        # Crea index.html se non esiste
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Scalable Data Ingestion & Vector Store Service v2.0</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 10px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                    padding: 30px;
                }
                h1 {
                    color: #333;
                    border-bottom: 2px solid #667eea;
                    padding-bottom: 10px;
                }
                .endpoints {
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                    gap: 20px;
                    margin-top: 30px;
                }
                .endpoint {
                    background: #f8f9fa;
                    border-left: 4px solid #667eea;
                    padding: 15px;
                    border-radius: 5px;
                    transition: transform 0.2s;
                }
                .endpoint:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                }
                .endpoint h3 {
                    margin: 0 0 10px 0;
                    color: #333;
                }
                .method {
                    display: inline-block;
                    padding: 3px 8px;
                    border-radius: 3px;
                    font-size: 12px;
                    font-weight: bold;
                    margin-right: 10px;
                }
                .get { background: #61affe; color: white; }
                .post { background: #49cc90; color: white; }
                .delete { background: #f93e3e; color: white; }
                a {
                    color: #667eea;
                    text-decoration: none;
                    font-weight: bold;
                }
                a:hover {
                    text-decoration: underline;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>[START] Scalable Data Ingestion & Vector Store Service v2.0</h1>
                <p>Self-hosted semantic document processing with vector search</p>
                
                <div style="margin: 20px 0; padding: 15px; background: #e3f2fd; border-radius: 5px;">
                    <strong>Quick Links:</strong><br>
                    <a href="/docs" style="margin-right: 15px;">📚 API Documentation</a>
                    <a href="/health" style="margin-right: 15px;">🩺 Health Check</a>
                    <a href="/stats" style="margin-right: 15px;">[STATS] System Stats</a>
                    <a href="/dlq/stats">⚠️ DLQ Stats</a>
                </div>
                
                <h2>📡 Available Endpoints</h2>
                <div class="endpoints">
                    <div class="endpoint">
                        <span class="method get">GET</span>
                        <h3>/health</h3>
                        <p>Health check endpoint</p>
                    </div>
                    <div class="endpoint">
                        <span class="method get">GET</span>
                        <h3>/stats</h3>
                        <p>Complete system statistics</p>
                    </div>
                    <div class="endpoint">
                        <span class="method get">GET</span>
                        <h3>/docs</h3>
                        <p>Interactive API documentation</p>
                    </div>
                    <div class="endpoint">
                        <span class="method post">POST</span>
                        <h3>/upload/text</h3>
                        <p>Upload and process text document</p>
                    </div>
                    <div class="endpoint">
                        <span class="method post">POST</span>
                        <h3>/upload/pdf</h3>
                        <p>Upload and process PDF document</p>
                    </div>
                    <div class="endpoint">
                        <span class="method post">POST</span>
                        <h3>/upload/csv</h3>
                        <p>Upload and process CSV document</p>
                    </div>
                    <div class="endpoint">
                        <span class="method post">POST</span>
                        <h3>/search</h3>
                        <p>Semantic search in documents</p>
                    </div>
                    <div class="endpoint">
                        <span class="method get">GET</span>
                        <h3>/dlq/stats</h3>
                        <p>Dead Letter Queue statistics</p>
                    </div>
                    <div class="endpoint">
                        <span class="method get">GET</span>
                        <h3>/dlq/failed-chunks</h3>
                        <p>List failed chunks with filters</p>
                    </div>
                    <div class="endpoint">
                        <span class="method get">GET</span>
                        <h3>/embeddings/info</h3>
                        <p>Embedder information</p>
                    </div>
                </div>
                
                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd;">
                    <h2>📈 System Status</h2>
                    <div id="status">Loading...</div>
                </div>
                
                <script>
                    // Fetch system status
                    fetch('/health')
                        .then(response => response.json())
                        .then(data => {
                            const statusDiv = document.getElementById('status');
                            statusDiv.innerHTML = `
                                <p><strong>Status:</strong> <span style="color: ${data.status === 'healthy' ? 'green' : 'orange'}">${data.status}</span></p>
                                <p><strong>Uptime:</strong> ${data.uptime_human || 'N/A'}</p>
                                <p><strong>Version:</strong> ${data.version}</p>
                            `;
                        })
                        .catch(error => {
                            document.getElementById('status').innerHTML = '<p style="color: red;">Failed to fetch system status</p>';
                        });
                </script>
            </div>
        </body>
        </html>
        """
        
        # Salva il file HTML
        index_path.write_text(html_content)
        logger.info(f"Created default index.html at {index_path}")
        
        return HTMLResponse(html_content)
    except Exception as e:
        logger.error(f"Error serving frontend: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/visual/asset", tags=["RAG Magellano"])
async def serve_visual_asset(path: str = Query(..., description="Relative asset path from retrieved chunk metadata")):
    """Serve a local visual asset referenced by RAG metadata, limited to configured roots."""
    raw_path = str(path or "").strip().strip('"').strip("'")
    if not raw_path:
        raise HTTPException(status_code=400, detail="Missing visual asset path")
    if raw_path.lower().startswith(("http://", "https://", "data:")):
        raise HTTPException(status_code=400, detail="Remote URLs must be rendered directly")

    normalized = raw_path.replace("\\", "/")
    candidates = []
    if normalized.startswith("/static/"):
        candidates.append(static_dir / normalized.removeprefix("/static/"))
    if normalized.startswith("static/"):
        candidates.append(static_dir / normalized.removeprefix("static/"))

    candidate_path = Path(raw_path)
    candidates.append(candidate_path if candidate_path.is_absolute() else Path.cwd() / candidate_path)

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        if not resolved.is_file():
            continue
        if any(resolved == root or root in resolved.parents for root in _visual_asset_roots):
            media_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
            return FileResponse(str(resolved), media_type=media_type)

    raise HTTPException(status_code=404, detail="Visual asset not found or outside allowed roots")


@app.get("/visual/source-status", tags=["RAG Magellano"])
async def visual_source_status(
    source: str = Query(..., description="Source filename/id stored in vector metadata"),
    render_missing: bool = Query(False, description="Render missing page images if the source PDF is available locally"),
    limit: int = Query(5000, ge=1, le=20000),
):
    """Diagnose whether an indexed PDF source has local visual page assets."""
    vs = get_vector_store()
    if vs is None or not getattr(vs, "collection", None):
        raise HTTPException(status_code=503, detail="Vector store not available")

    try:
        batch = vs.collection.get(where={"source": source}, include=["metadatas"], limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unable to read vector metadata: {e}")

    metadatas = batch.get("metadatas") or []
    pages = set()
    visual_pages = set()
    for metadata in metadatas:
        metadata = metadata or {}
        page = _metadata_value(metadata, "page", "pages")
        if page is None:
            continue
        try:
            page_num = int(str(page))
        except (TypeError, ValueError):
            continue
        pages.add(page_num)
        has_visual = any(
            _metadata_value(metadata, key)
            for key in ("image_url", "page_image_url", "visual_url", "asset_path", "local_asset_path")
        )
        if not has_visual:
            if render_missing:
                has_visual = bool(_local_page_image_metadata(source, page_num, metadata))
            else:
                safe_stem = _safe_asset_stem(source)
                filename = f"page_{page_num:04d}.png"
                export_root = Path(os.getenv("VISUAL_EXPORT_ROOT") or (Path.cwd() / "data" / "visual"))
                candidates = [export_root / "pdf_pages" / safe_stem / filename]
                for root in _visual_asset_roots:
                    candidates.append(root / "pdf_pages" / safe_stem / filename)
                    candidates.append(root / "visual" / "pdf_pages" / safe_stem / filename)
                has_visual = any(candidate.exists() and candidate.stat().st_size > 0 for candidate in candidates)
        if has_visual:
            visual_pages.add(page_num)

    pdf_source = _find_local_pdf_source(source, metadatas[0] if metadatas else {})
    missing_pages = sorted(pages - visual_pages)
    return {
        "source": source,
        "indexed_chunks": len(metadatas),
        "indexed_pages": len(pages),
        "visual_pages": len(visual_pages),
        "missing_visual_pages": len(missing_pages),
        "missing_visual_page_sample": missing_pages[:25],
        "source_pdf_available": pdf_source is not None,
        "source_pdf_path": pdf_source.as_posix() if pdf_source else None,
        "render_missing": render_missing,
        "status": "visual-ready" if pages and not missing_pages else "missing-visual-assets",
        "hint": (
            "Reimporta il PDF con /upload/pdf usando source_name uguale a questa source, "
            "oppure configura PDF_SOURCE_ROOTS con il PDF originale e richiama render_missing=true."
            if missing_pages else ""
        ),
    }


# ====================== HEALTH & SYSTEM ENDPOINTS ======================
@app.get("/health", tags=["Health & Monitoring"])
async def health_check():
    """Health check endpoint"""
    try:
        uptime = datetime.utcnow() - app_start_time
        
        # Check service health
        services_status = {
            "embedder": embedder is not None,
            "vector_store": vector_store is not None,
            "dlq": dlq is not None,
            "processor": DocumentProcessor is not None
        }
        
        # Verifica se i servizi critici sono operativi
        critical_services = ["embedder", "vector_store"]
        critical_status = all(services_status[s] for s in critical_services)
        
        status = "healthy" if critical_status else "degraded"
        
        return {
            "status": status,
            "service": "Vector Ingestion Service",
            "version": "2.0.0",
            "uptime_seconds": int(uptime.total_seconds()),
            "uptime_human": str(uptime).split('.')[0],
            "services": services_status,
            "timestamp": datetime.utcnow().isoformat(),
            "environment": CONFIG["ENVIRONMENT"]
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=200,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@app.get("/stats", tags=["Health & Monitoring"])
async def get_system_stats():
    """Statistiche complete del sistema"""
    try:
        if embedder is None or vector_store is None or dlq is None:
            raise HTTPException(status_code=503, detail="Services not initialized")
        
        embedder_info = (
            await asyncio.to_thread(embedder.get_model_info)
            if embedder else {"error": "Not initialized"}
        )
        vector_stats = (
            await asyncio.to_thread(vector_store.get_collection_stats)
            if vector_store else {"error": "Not initialized"}
        )
        dlq_stats = (
            await asyncio.to_thread(dlq.get_statistics)
            if dlq else {"error": "Not initialized"}
        )
        
        # Memory usage (if psutil available)
        memory_info = {"memory_usage_mb": "N/A"}
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory_info = {
                "memory_usage_mb": round(process.memory_info().rss / 1024 / 1024, 2),
                "memory_percent": round(process.memory_percent(), 2)
            }
        except ImportError:
            pass
        
        # Estrai total_chunks in modo robusto
        total_chunks = 0
        if isinstance(vector_stats, dict):
            if vector_stats.get("status") == "success":
                total_chunks = vector_stats.get("stats", {}).get("total_chunks", 0)
            else:
                # Formato alternativo per retrocompatibilità
                total_chunks = vector_stats.get("total_chunks", 0)
        
        # Calcola failed_operations
        failed_operations = 0
        if isinstance(dlq_stats, dict):
            # Controlla se dlq_stats ha la struttura corretta
            if "failed_chunks" in dlq_stats and isinstance(dlq_stats["failed_chunks"], dict):
                failed_operations += dlq_stats["failed_chunks"].get("total", 0)
            if "failed_files" in dlq_stats and isinstance(dlq_stats["failed_files"], dict):
                failed_operations += dlq_stats["failed_files"].get("total", 0)
        
        if VECTOR_STATS_DEEP_DOCUMENT_COUNT:
            total_documents = await asyncio.to_thread(_vector_document_count) or len(processed_files)
            total_documents_mode = "deep"
        else:
            cached_documents = vector_document_count_cache.get("*")
            total_documents = (
                int(cached_documents.get("value") or 0)
                if cached_documents
                else len(processed_files)
            )
            total_documents_mode = "cached"

        return {
            "embedder": embedder_info,
            "vector_store": vector_stats,
            "dlq": dlq_stats,
            "pdf_ingest": _pdf_ingest_summary(),
            "system": {
                "uptime_seconds": int((datetime.utcnow() - app_start_time).total_seconds()),
                "uptime_human": str(datetime.utcnow() - app_start_time).split('.')[0],
                "total_processed_files": total_documents,
                "total_documents": total_documents,
                "total_documents_mode": total_documents_mode,
                "total_chunks": total_chunks,
                "failed_operations": failed_operations,
                "memory_info": memory_info,
                "config": {
                    "max_file_size_mb": CONFIG["MAX_FILE_SIZE_MB"],
                    "default_chunk_size": CONFIG["DEFAULT_CHUNK_SIZE"],
                    "default_batch_size": CONFIG["DEFAULT_BATCH_SIZE"],
                    "vector_stats_cache_ttl_seconds": VECTOR_STATS_CACHE_TTL_SECONDS,
                    "vector_stats_deep_document_count": VECTOR_STATS_DEEP_DOCUMENT_COUNT,
                    "rag_default_retrieval_chunks": RAG_DEFAULT_RETRIEVAL_CHUNKS,
                    "rag_generation_context_chunks": RAG_GENERATION_CONTEXT_CHUNKS,
                    "rag_max_tokens": RAG_MAX_TOKENS,
                    "rag_max_temperature": RAG_MAX_TEMPERATURE
                }
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ingest/pdf-jobs", tags=["Document Ingestion"])
async def list_pdf_ingest_jobs(
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None)
):
    """Stato della coda PDF visuale usata dagli import automatici n8n."""
    jobs = [_pdf_ingest_public_job(job) for job in pdf_ingest_jobs.values()]
    if status:
        jobs = [job for job in jobs if job.get("status") == status]
    jobs.sort(key=lambda job: str(job.get("created_at") or ""), reverse=True)
    return {
        "summary": _pdf_ingest_summary(),
        "jobs": jobs[:limit],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ====================== DLQ ENDPOINTS ======================
@app.get("/dlq/stats", tags=["DLQ Management"])
async def get_dlq_statistics():
    """Statistiche del Dead Letter Queue"""
    try:
        if dlq is None:
            raise HTTPException(status_code=503, detail="DLQ service not initialized")
        
        stats = dlq.get_statistics()
        
        return {
            **stats,
            "timestamp": datetime.utcnow().isoformat(),
            "retention_days": 30
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting DLQ stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dlq/failed-chunks", tags=["DLQ Management"])
async def list_failed_chunks(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    reason: Optional[str] = Query(None),
    status: Optional[str] = Query(None)
):
    """Lista chunk falliti con filtri"""
    try:
        if dlq is None:
            raise HTTPException(status_code=503, detail="DLQ service not initialized")
        
        chunks = dlq.get_failed_chunks(
            limit=limit,
            offset=offset,
            reason=reason,
            status=status
        )
        
        total_stats = dlq.get_statistics()
        
        return {
            "chunks": chunks,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total_stats.get("failed_chunks", {}).get("total", 0),
                "has_more": (offset + limit) < total_stats.get("failed_chunks", {}).get("total", 0)
            },
            "filters": {
                "reason": reason,
                "status": status
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing failed chunks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dlq/failed-files", tags=["DLQ Management"])
async def list_failed_files(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    days: int = Query(7, ge=1, le=365)
):
    """Lista file falliti"""
    try:
        if dlq is None:
            raise HTTPException(status_code=503, detail="DLQ service not initialized")
        
        files = dlq.get_failed_files(limit=limit, offset=offset)
        
        # Filtra per data se necessario
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        filtered_files = [
            f for f in files 
            if "timestamp" in f and datetime.fromisoformat(f["timestamp"].replace('Z', '+00:00')) > cutoff_date
        ]
        
        total_stats = dlq.get_statistics()
        
        return {
            "files": filtered_files[:limit],
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total_stats.get("failed_files", {}).get("total", 0),
                "has_more": (offset + limit) < total_stats.get("failed_files", {}).get("total", 0)
            },
            "filter": {
                "last_days": days,
                "cutoff_date": cutoff_date.isoformat()
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing failed files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dlq/retry/{chunk_id}", tags=["DLQ Management"])
async def retry_failed_chunk(chunk_id: str, background_tasks: BackgroundTasks):
    """Ritenta processing di un chunk fallito"""
    try:
        if dlq is None:
            raise HTTPException(status_code=503, detail="DLQ service not initialized")
        
        # Recupera il chunk fallito - usando get_failed_chunks e filtrando
        chunks = dlq.get_failed_chunks(limit=1000)
        failed_chunk = next(
            (c for c in chunks if c.get('id') == chunk_id or c.get('chunk_id') == chunk_id), 
            None
        )
        
        if not failed_chunk:
            raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} not found")
        
        # Segna per retry usando retry_chunk
        success = dlq.retry_chunk(failed_chunk['id'])
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to mark chunk {chunk_id} for retry")
        
        # Aggiungi task di background per il re-processing
        background_tasks.add_task(process_retry_chunk, failed_chunk['id'], failed_chunk)
        
        return {
            "message": f"Retry initiated for chunk {chunk_id}",
            "chunk_id": chunk_id,
            "status": "retrying",
            "retry_count": failed_chunk.get("retry_count", 0) + 1,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying chunk {chunk_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_retry_chunk(chunk_id: str, chunk_data: Dict[str, Any]):
    """Background task per processare un chunk in retry: re-embedding e re-insertion in ChromaDB"""
    try:
        logger.info(f"Processing retry for chunk {chunk_id}")

        if not dlq:
            logger.error("DLQ not initialized, cannot retry chunk")
            return

        failed = dlq.get_failed_chunk(chunk_id)
        if not failed or not failed.get('content'):
            logger.warning(f"Chunk {chunk_id} not found or empty in DLQ")
            return

        if not embedder:
            logger.error("Embedder not initialized, cannot retry chunk")
            return

        if not vector_store:
            logger.error("Vector store not initialized, cannot retry chunk")
            return

        # Re-genera embedding del contenuto
        embedding = embedder.embed_single(failed['content'])

        # Re-inserisce in ChromaDB
        result = vector_store.add_chunks([{
            'id': failed.get('chunk_id', chunk_id),
            'content': failed['content'],
            'embedding': embedding.tolist(),
            'metadata': failed.get('metadata') or {}
        }])

        if result.get('status') == 'success':
            dlq.remove_failed_chunk(chunk_id)
            logger.info(f"Successfully reprocessed chunk {chunk_id}")
        else:
            logger.error(f"Failed to re-add chunk {chunk_id} to vector store: {result.get('message')}")

    except Exception as e:
        logger.error(f"Failed to reprocess chunk {chunk_id}: {e}")


@app.delete("/dlq/clear-permanent", tags=["DLQ Management"])
async def clear_permanent_failures(
    max_retries: int = Query(3, ge=1, le=10),
    older_than_days: int = Query(30, ge=1, le=365)
):
    """Cancella fallimenti permanenti"""
    try:
        if dlq is None:
            raise HTTPException(status_code=503, detail="DLQ service not initialized")
        
        result = dlq.clear_permanent_failures(max_retries)
        
        # Aggiungi controllo per older_than_days se necessario
        if older_than_days < 30:
            logger.warning(f"Clearing failures newer than {older_than_days} days")
        
        return {
            "message": "Permanent failures cleared",
            "deleted_count": result.get("deleted_count", 0),
            "parameters": {
                "max_retries": max_retries,
                "older_than_days": older_than_days
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing permanent failures: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dlq/test-failure", tags=["DLQ Management"])
async def test_dlq_functionality():
    """Test DLQ aggiungendo un fallimento simulato"""
    try:
        if dlq is None:
            raise HTTPException(status_code=503, detail="DLQ service not initialized")
        
        test_id = str(uuid.uuid4())[:8]
        
        dlq.add_failed_chunk(
            chunk_id=f"test_chunk_{test_id}",
            content="This is a test chunk for DLQ functionality testing.",
            error="Simulated parsing error for testing purposes",
            reason="PARSING_ERROR",
            metadata={
                "test": True,
                "source": "test_endpoint",
                "timestamp": datetime.utcnow().isoformat()
            },
            source="test"
        )
        
        return {
            "message": "Test failure added to DLQ",
            "test_chunk_id": f"test_chunk_{test_id}",
            "dlq_stats": dlq.get_statistics(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing DLQ functionality: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ====================== DOCUMENT INGESTION ENDPOINTS ======================
@app.post("/upload/text", tags=["Document Ingestion"])
async def upload_text_document(
    content: str = Form(...),
    source_id: str = Form(None),
    pdf_url: Optional[str] = Form(None),
    prefer_pdf: bool = Form(True),
    pdf_ingest_mode: str = Form(PDF_URL_INGEST_MODE),
    filename: Optional[str] = Form(None),
    chunk_size: int = Form(CONFIG["DEFAULT_CHUNK_SIZE"]),
    chunk_overlap: int = Form(CONFIG["DEFAULT_CHUNK_OVERLAP"]),
    batch_size: int = Form(CONFIG["DEFAULT_BATCH_SIZE"]),
    extract_page_images: bool = Form(True),
    extract_tables: bool = Form(True),
    extract_formulas: bool = Form(True)
):
    """Upload testo; con pdf_url puo' accodare la pipeline PDF visuale senza bloccare la GUI."""
    start_time = datetime.utcnow()
    
    try:
        if embedder is None or vector_store is None:
            raise HTTPException(status_code=503, detail="Services not initialized")
        
        if not content or not content.strip():
            raise HTTPException(status_code=400, detail="Empty content provided")
        
        # Genera source_id se non fornito
        if not source_id:
            source_id = f"text_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # Valida parametri
        if chunk_size < 10 or chunk_size > 10000:
            raise HTTPException(status_code=400, detail="chunk_size must be between 10 and 10000")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise HTTPException(status_code=400, detail="chunk_overlap must be >= 0 and < chunk_size")
        if batch_size < 1 or batch_size > CONFIG["MAX_BATCH_SIZE"]:
            raise HTTPException(status_code=400, detail=f"batch_size must be between 1 and {CONFIG['MAX_BATCH_SIZE']}")

        pdf_ingest = None
        if pdf_url and _as_bool(prefer_pdf):
            mode = str(pdf_ingest_mode or PDF_URL_INGEST_MODE or "deferred").strip().lower()
            if mode in {"sync", "synchronous", "blocking"}:
                return await upload_pdf_from_url(
                    pdf_url=pdf_url,
                    source_id=source_id,
                    filename=filename or (f"{source_id}.pdf" if source_id else None),
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    batch_size=batch_size,
                    extract_page_images=extract_page_images,
                    extract_tables=extract_tables,
                    extract_formulas=extract_formulas,
                )
            if mode not in {"skip", "false", "off", "none", "text"}:
                pdf_ingest = await _enqueue_pdf_ingest_job(
                    pdf_url=pdf_url,
                    source_id=source_id,
                    filename=filename or (f"{source_id}.pdf" if source_id else None),
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    batch_size=batch_size,
                    extract_page_images=_as_bool(extract_page_images),
                    extract_tables=_as_bool(extract_tables),
                    extract_formulas=_as_bool(extract_formulas),
                )
        
        logger.info(f"Processing text document: {source_id}, size: {len(content)} chars")
        
        if DocumentProcessor is None:
            raise HTTPException(status_code=503, detail="Document processor not available")
        
        processor = DocumentProcessor(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        text_metadata = {}
        if pdf_url:
            text_metadata.update({
                "pdf_url": pdf_url,
                "source_id": source_id,
                "filename": filename or (f"{source_id}.pdf" if source_id else None),
                "content_type": "text_preview",
                "pdf_ingest_mode": str(pdf_ingest_mode or PDF_URL_INGEST_MODE or "deferred").strip().lower(),
            })
            if pdf_ingest:
                text_metadata.update({
                    "pdf_ingest_job_id": pdf_ingest.get("job_id"),
                    "pdf_ingest_status": pdf_ingest.get("status"),
                })

        chunks = processor.process_text(content, source_id, metadata=text_metadata or None)
        
        if not chunks:
            raise HTTPException(status_code=400, detail="No content could be extracted from text")
        
        # Aggiungi chunk al vector store
        result = _add_chunks_batch(chunks, batch_size=min(batch_size, len(chunks)))
        
        # Registra file processato
        file_info = {
            "type": "text",
            "source_id": source_id,
            "chunks": len(chunks),
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "content_length": len(content),
            "timestamp": datetime.utcnow().isoformat(),
            "processing_time_ms": round((datetime.utcnow() - start_time).total_seconds() * 1000, 2)
        }
        processed_files.append(file_info)
        
        logger.info(f"Processed text document {source_id}: {len(chunks)} chunks")
        
        response = {
            "status": "success",
            "message": f"Processed {len(chunks)} chunks from text document",
            "source_id": source_id,
            "chunks_processed": len(chunks),
            "chunks_created": len(chunks),
            "content_preview": content[:200] + "..." if len(content) > 200 else content,
            "processing_time_ms": round((datetime.utcnow() - start_time).total_seconds() * 1000, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
        if pdf_ingest:
            response["pdf_ingest"] = pdf_ingest
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing text document: {e}")
        
        if dlq:
            dlq.add_failed_chunk(
                chunk_id=f"{source_id}_text_error",
                content=content[:1000] if content else "",
                error=str(e),
                reason="PARSING_ERROR",
                metadata={
                    "source_id": source_id,
                    "content_type": "text",
                    "content_length": len(content) if content else 0,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload/pdf", tags=["Document Ingestion"])
async def upload_pdf_document(
    file: UploadFile = File(...),
    source_name: Optional[str] = Form(None),
    chunk_size: int = Form(CONFIG["DEFAULT_CHUNK_SIZE"]),
    chunk_overlap: int = Form(CONFIG["DEFAULT_CHUNK_OVERLAP"]),
    batch_size: int = Form(CONFIG["DEFAULT_BATCH_SIZE"]),
    extract_page_images: bool = Form(True),
    extract_tables: bool = Form(True),
    extract_formulas: bool = Form(True)
):
    """Upload e processa PDF"""
    start_time = datetime.utcnow()
    contents = b""

    try:
        if embedder is None or vector_store is None:
            raise HTTPException(status_code=503, detail="Services not initialized")

        # Valida file
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="File must be PDF (.pdf)")
        
        contents = await file.read()
        
        # Controlla dimensione file
        max_size = CONFIG["MAX_FILE_SIZE_MB"] * 1024 * 1024
        if len(contents) > max_size:
            raise HTTPException(
                status_code=400, 
                detail=f"File too large (max {CONFIG['MAX_FILE_SIZE_MB']}MB)"
            )
        
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Empty file")
        
        resolved_filename = source_name or file.filename
        logger.info(f"Processing PDF: {resolved_filename}, size: {len(contents)} bytes")
        
        if DocumentProcessor is None:
            raise HTTPException(status_code=503, detail="Document processor not available")
        
        processor = DocumentProcessor(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        chunks = processor.process_pdf(
            contents,
            resolved_filename,
            extract_page_images=_as_bool(extract_page_images),
            extract_tables=_as_bool(extract_tables),
            extract_formulas=_as_bool(extract_formulas),
        )
        
        if not chunks:
            raise HTTPException(status_code=400, detail="No content could be extracted from PDF")
        
        # Aggiungi chunk al vector store
        result = _add_chunks_batch(chunks, batch_size=min(batch_size, len(chunks)))
        
        # Calcola numero di pagine
        pages = len(set(c.get('metadata', {}).get('page', 0) for c in chunks))
        page_images = len({
            c.get("metadata", {}).get("local_asset_path")
            for c in chunks
            if c.get("metadata", {}).get("visual_asset_kind") == "pdf_page_image"
            and c.get("metadata", {}).get("local_asset_path")
        })
        table_chunks = sum(1 for c in chunks if c.get("metadata", {}).get("structured_kind") == "table")
        formula_chunks = sum(1 for c in chunks if c.get("metadata", {}).get("formula_count"))
        
        # Registra file processato
        file_info = {
            "type": "pdf",
            "filename": resolved_filename,
            "upload_filename": file.filename,
            "chunks": len(chunks),
            "pages": pages,
            "page_images": page_images,
            "table_chunks": table_chunks,
            "formula_chunks": formula_chunks,
            "file_size": len(contents),
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "extract_page_images": _as_bool(extract_page_images),
            "extract_tables": _as_bool(extract_tables),
            "extract_formulas": _as_bool(extract_formulas),
            "timestamp": datetime.utcnow().isoformat(),
            "processing_time_ms": round((datetime.utcnow() - start_time).total_seconds() * 1000, 2)
        }
        processed_files.append(file_info)
        
        logger.info(f"Processed PDF {resolved_filename}: {len(chunks)} chunks, {pages} pages")
        
        return {
            "status": "success",
            "message": f"Processed {len(chunks)} chunks from PDF",
            "filename": resolved_filename,
            "upload_filename": file.filename,
            "chunks_processed": len(chunks),
            "chunks_created": len(chunks),
            "pages": pages,
            "page_images": page_images,
            "table_chunks": table_chunks,
            "formula_chunks": formula_chunks,
            "file_size_bytes": len(contents),
            "processing_time_ms": round((datetime.utcnow() - start_time).total_seconds() * 1000, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing PDF {file.filename if file else 'unknown'}: {e}")
        
        if dlq:
            file_size = len(contents)
            dlq.add_failed_file(
                filename=file.filename,
                error=str(e),
                reason="PARSING_ERROR",
                file_size_bytes=file_size,
                metadata={
                    "filename": file.filename,
                    "content_type": "pdf",
                    "file_size": file_size,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload/pdf-url", tags=["Document Ingestion"])
async def upload_pdf_from_url(
    pdf_url: str = Form(...),
    source_id: Optional[str] = Form(None),
    filename: Optional[str] = Form(None),
    chunk_size: int = Form(CONFIG["DEFAULT_CHUNK_SIZE"]),
    chunk_overlap: int = Form(CONFIG["DEFAULT_CHUNK_OVERLAP"]),
    batch_size: int = Form(CONFIG["DEFAULT_BATCH_SIZE"]),
    extract_page_images: bool = Form(True),
    extract_tables: bool = Form(True),
    extract_formulas: bool = Form(True)
):
    """Scarica un PDF remoto pubblico e lo processa con la pipeline visuale."""
    start_time = datetime.utcnow()
    contents = b""
    resolved_filename = filename or _filename_from_pdf_url(pdf_url, source_id)

    try:
        if embedder is None or vector_store is None:
            raise HTTPException(status_code=503, detail="Services not initialized")
        if DocumentProcessor is None:
            raise HTTPException(status_code=503, detail="Document processor not available")

        max_size = CONFIG["MAX_FILE_SIZE_MB"] * 1024 * 1024
        contents = await _download_pdf_from_url(pdf_url, max_size)
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Empty PDF download")

        processor = DocumentProcessor(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        chunks = processor.process_pdf(
            contents,
            resolved_filename,
            extract_page_images=_as_bool(extract_page_images),
            extract_tables=_as_bool(extract_tables),
            extract_formulas=_as_bool(extract_formulas),
        )
        if not chunks:
            raise HTTPException(status_code=400, detail="No content could be extracted from PDF")

        for chunk in chunks:
            metadata = chunk.setdefault("metadata", {})
            metadata["pdf_url"] = pdf_url
            if source_id:
                metadata["source_id"] = source_id
                metadata.setdefault("source", resolved_filename)

        _add_chunks_batch(chunks, batch_size=min(batch_size, len(chunks)))

        pages = len(set(c.get('metadata', {}).get('page', 0) for c in chunks))
        page_images = len({
            c.get("metadata", {}).get("local_asset_path")
            for c in chunks
            if c.get("metadata", {}).get("visual_asset_kind") == "pdf_page_image"
            and c.get("metadata", {}).get("local_asset_path")
        })
        table_chunks = sum(1 for c in chunks if c.get("metadata", {}).get("structured_kind") == "table")
        formula_chunks = sum(1 for c in chunks if c.get("metadata", {}).get("formula_count"))

        file_info = {
            "type": "pdf",
            "filename": resolved_filename,
            "source_id": source_id,
            "pdf_url": pdf_url,
            "chunks": len(chunks),
            "pages": pages,
            "page_images": page_images,
            "table_chunks": table_chunks,
            "formula_chunks": formula_chunks,
            "file_size": len(contents),
            "timestamp": datetime.utcnow().isoformat(),
            "processing_time_ms": round((datetime.utcnow() - start_time).total_seconds() * 1000, 2),
        }
        processed_files.append(file_info)

        logger.info(f"Processed remote PDF {resolved_filename}: {len(chunks)} chunks, {pages} pages")
        return {
            "status": "success",
            "message": f"Processed {len(chunks)} chunks from remote PDF",
            "source_id": source_id,
            "filename": resolved_filename,
            "pdf_url": pdf_url,
            "chunks_processed": len(chunks),
            "chunks_created": len(chunks),
            "pages": pages,
            "page_images": page_images,
            "table_chunks": table_chunks,
            "formula_chunks": formula_chunks,
            "file_size_bytes": len(contents),
            "processing_time_ms": round((datetime.utcnow() - start_time).total_seconds() * 1000, 2),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing remote PDF {resolved_filename}: {e}")
        if dlq:
            dlq.add_failed_file(
                filename=resolved_filename,
                error=str(e),
                reason="PARSING_ERROR",
                file_size_bytes=len(contents),
                metadata={
                    "filename": resolved_filename,
                    "pdf_url": pdf_url,
                    "source_id": source_id,
                    "content_type": "pdf_url",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload/csv", tags=["Document Ingestion"])
async def upload_csv_document(
    file: UploadFile = File(...),
    group_by: Optional[str] = Form(None),
    max_rows_per_chunk: int = Form(50),
    batch_size: int = Form(CONFIG["DEFAULT_BATCH_SIZE"])
):
    """Upload e processa CSV"""
    start_time = datetime.utcnow()
    contents = b""

    try:
        if embedder is None or vector_store is None:
            raise HTTPException(status_code=503, detail="Services not initialized")

        # Valida file
        if not file.filename or not file.filename.lower().endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be CSV (.csv)")
        
        contents = await file.read()
        
        # Controlla dimensione file
        max_size = CONFIG["MAX_FILE_SIZE_MB"] * 1024 * 1024
        if len(contents) > max_size:
            raise HTTPException(
                status_code=400, 
                detail=f"File too large (max {CONFIG['MAX_FILE_SIZE_MB']}MB)"
            )
        
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Empty file")
        
        logger.info(f"Processing CSV: {file.filename}, size: {len(contents)} bytes")
        
        if DocumentProcessor is None:
            raise HTTPException(status_code=503, detail="Document processor not available")
        
        processor = DocumentProcessor()
        chunks = processor.process_csv(
            contents,
            file.filename,
            group_by=group_by,
            max_rows_per_chunk=max_rows_per_chunk
        )
        
        if not chunks:
            raise HTTPException(status_code=400, detail="No content could be extracted from CSV")
        
        # Aggiungi chunk al vector store
        result = _add_chunks_batch(chunks, batch_size=min(batch_size, len(chunks)))
        
        # Registra file processato
        file_info = {
            "type": "csv",
            "filename": file.filename,
            "chunks": len(chunks),
            "group_by": group_by,
            "max_rows_per_chunk": max_rows_per_chunk,
            "file_size": len(contents),
            "timestamp": datetime.utcnow().isoformat(),
            "processing_time_ms": round((datetime.utcnow() - start_time).total_seconds() * 1000, 2)
        }
        processed_files.append(file_info)
        
        logger.info(f"Processed CSV {file.filename}: {len(chunks)} chunks")
        
        return {
            "status": "success",
            "message": f"Processed {len(chunks)} chunks from CSV",
            "filename": file.filename,
            "chunks_processed": len(chunks),
            "chunks_created": len(chunks),
            "group_by": group_by,
            "rows_per_chunk": max_rows_per_chunk,
            "file_size_bytes": len(contents),
            "processing_time_ms": round((datetime.utcnow() - start_time).total_seconds() * 1000, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing CSV {file.filename if file else 'unknown'}: {e}")
        
        if dlq:
            file_size = len(contents)
            dlq.add_failed_file(
                filename=file.filename,
                error=str(e),
                reason="PARSING_ERROR",
                file_size_bytes=file_size,
                metadata={
                    "filename": file.filename,
                    "content_type": "csv",
                    "file_size": file_size,
                    "group_by": group_by,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload/batch", tags=["Document Ingestion"])
async def upload_batch_documents(
    files: List[UploadFile] = File(...),
    chunk_size: int = Form(CONFIG["DEFAULT_CHUNK_SIZE"]),
    chunk_overlap: int = Form(CONFIG["DEFAULT_CHUNK_OVERLAP"]),
    batch_size: int = Form(CONFIG["DEFAULT_BATCH_SIZE"])
):
    """
    Upload e processa fino a 20 file in un singolo request.
    Formati supportati: .pdf, .csv, .txt, .json (e altri testi plain).
    Ogni file viene elaborato indipendentemente — un errore su un file non blocca gli altri.
    """
    batch_start = datetime.utcnow()

    if embedder is None or vector_store is None:
        raise HTTPException(status_code=503, detail="Services not initialized")
    if DocumentProcessor is None:
        raise HTTPException(status_code=503, detail="Document processor not available")
    if not files:
        raise HTTPException(status_code=400, detail="Nessun file fornito")
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Massimo 20 file per request")

    # Valida parametri condivisi
    if chunk_size < 10 or chunk_size > 10000:
        raise HTTPException(status_code=400, detail="chunk_size deve essere tra 10 e 10000")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise HTTPException(status_code=400, detail="chunk_overlap deve essere >= 0 e < chunk_size")
    if batch_size < 1 or batch_size > CONFIG["MAX_BATCH_SIZE"]:
        raise HTTPException(status_code=400, detail=f"batch_size deve essere tra 1 e {CONFIG['MAX_BATCH_SIZE']}")

    processor = DocumentProcessor(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    results = []
    total_chunks = 0

    for file in files:
        file_start = datetime.utcnow()
        filename = file.filename or "unknown"
        ext = Path(filename).suffix.lower()

        try:
            contents = await file.read()
            max_bytes = CONFIG["MAX_FILE_SIZE_MB"] * 1024 * 1024
            if len(contents) > max_bytes:
                raise ValueError(f"File supera il limite di {CONFIG['MAX_FILE_SIZE_MB']}MB")

            if ext == ".pdf":
                chunks = processor.process_pdf(contents, filename)
            elif ext == ".csv":
                chunks = processor.process_csv(contents, filename)
            else:
                # .txt, .json, .md e qualsiasi testo plain
                try:
                    text = contents.decode("utf-8")
                except UnicodeDecodeError:
                    text = contents.decode("latin-1", errors="replace")
                source_id = f"{Path(filename).stem}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
                chunks = processor.process_text(text, source_id)

            if not chunks:
                raise ValueError("Nessun contenuto estraibile dal file")

            _add_chunks_batch(chunks, batch_size=min(batch_size, len(chunks)))
            elapsed_ms = round((datetime.utcnow() - file_start).total_seconds() * 1000, 2)
            total_chunks += len(chunks)

            results.append({
                "filename": filename,
                "status": "success",
                "chunks_processed": len(chunks),
                "error": None,
                "processing_time_ms": elapsed_ms
            })
            logger.info(f"Batch upload: {filename} → {len(chunks)} chunks ({elapsed_ms}ms)")

        except Exception as e:
            elapsed_ms = round((datetime.utcnow() - file_start).total_seconds() * 1000, 2)
            results.append({
                "filename": filename,
                "status": "error",
                "chunks_processed": None,
                "error": str(e),
                "processing_time_ms": elapsed_ms
            })
            logger.warning(f"Batch upload: {filename} → errore: {e}")
            if dlq:
                dlq.add_failed_file(
                    filename=filename,
                    error=str(e),
                    reason="PARSING_ERROR",
                    file_size_bytes=len(contents) if "contents" in dir() else 0,
                    metadata={"batch": True, "ext": ext, "timestamp": datetime.utcnow().isoformat()}
                )

    successful = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - successful
    total_ms = round((datetime.utcnow() - batch_start).total_seconds() * 1000, 2)

    return {
        "total_files": len(files),
        "successful": successful,
        "failed": failed,
        "total_chunks": total_chunks,
        "results": results,
        "processing_time_ms": total_ms,
        "timestamp": datetime.utcnow().isoformat()
    }


# ====================== SEARCH & QUERY ENDPOINTS ======================
@app.post("/search", tags=["Search & Query"])
async def semantic_search(
    request: Request,
    query: Optional[str] = Form(None),
    n_results: int = Form(5, ge=1, le=CONFIG["MAX_SEARCH_RESULTS"]),
    source_filter: Optional[str] = Form(None),
    min_similarity: float = Form(0.0, ge=0.0, le=1.0),
    include_metadata: bool = Form(True),
    use_reranker: bool = Form(False)
):
    """
    Ricerca semantica nei documenti.

    - `use_reranker=true`: attiva cross-encoder re-ranking (più preciso, ~2x più lento).
      Over-fetcha 3x candidati da ChromaDB e li ri-ordina con ms-marco-MiniLM-L-6-v2.
    """
    try:
        payload = await _optional_json(request)
        query = _payload_value(payload, "query", query)
        n_results = _payload_value(payload, "n_results", payload.get("top_k", n_results))
        source_filter = _payload_value(payload, "source_filter", payload.get("source", source_filter))
        min_similarity = _payload_value(payload, "min_similarity", min_similarity)
        include_metadata = _payload_value(payload, "include_metadata", include_metadata)
        use_reranker = _payload_value(payload, "use_reranker", use_reranker)

        n_results = _as_int(n_results, "n_results", 1, CONFIG["MAX_SEARCH_RESULTS"])
        min_similarity = _as_float(min_similarity, "min_similarity", 0.0, 1.0)
        include_metadata = _as_bool(include_metadata)
        use_reranker = _as_bool(use_reranker)

        if vector_store is None:
            raise HTTPException(status_code=503, detail="Vector store not initialized")

        if not query or not query.strip():
            raise HTTPException(status_code=400, detail="Empty query")

        where_filter = None
        if source_filter:
            where_filter = {"source": source_filter}

        logger.info(f"Search: '{query[:50]}' n={n_results} reranker={use_reranker}")

        if use_reranker:
            results = vector_store.query_with_reranking(
                query_text=query,
                n_results=n_results,
                where=where_filter,
                include_metadata=include_metadata,
                min_similarity=min_similarity
            )
        else:
            results = vector_store.query(
                query_text=query,
                n_results=n_results,
                where=where_filter,
                include_metadata=include_metadata,
                min_similarity=min_similarity
            )

        filtered_results = []
        for r in results:
            similarity = r.get("similarity")
            if similarity is None:
                similarity = 1 - r.get('distance', 0)
            r['similarity'] = round(similarity, 4)
            if not include_metadata:
                r.pop('metadata', None)
            filtered_results.append(r)

        return {
            "query": query,
            "results_count": len(filtered_results),
            "results": filtered_results,
            "filters": {
                "source": source_filter,
                "min_similarity": min_similarity,
                "include_metadata": include_metadata,
                "use_reranker": use_reranker
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error performing search: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents", tags=["Search & Query"])
async def list_documents(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    document_type: Optional[str] = Query(None)
):
    """Lista tutti i documenti caricati"""
    try:
        # Ottieni statistiche vector store
        stats = {}
        if vector_store:
            stats = vector_store.get_collection_stats()
        
        # Estrai total_chunks correttamente
        total_chunks = 0
        if isinstance(stats, dict) and stats.get("status") == "success":
            total_chunks = stats.get("stats", {}).get("total_chunks", 0)

        persistent_docs = _vector_document_summaries(
            limit=limit,
            offset=offset,
            document_type=document_type,
        )
        if persistent_docs["total_documents"] > 0 or total_chunks > 0:
            return {
                "documents": persistent_docs["documents"],
                "total_documents": persistent_docs["total_documents"],
                "total_chunks": persistent_docs["total_chunks"] or total_chunks,
                "filters": {
                    "type": document_type
                },
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "has_more": (offset + limit) < persistent_docs["total_documents"],
                    "total_pages": (
                        (persistent_docs["total_documents"] + limit - 1) // limit
                        if limit > 0 else 0
                    )
                },
                "source": "vector_store"
            }

        # Fallback per la sessione corrente quando il vector store non e' disponibile.
        filtered_files = processed_files
        if document_type:
            filtered_files = [f for f in processed_files if f.get("type") == document_type]
        paginated_files = filtered_files[offset:offset + limit]
        
        return {
            "documents": paginated_files,
            "total_documents": len(filtered_files),
            "total_chunks": total_chunks,
            "filters": {
                "type": document_type
            },
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < len(filtered_files),
                "total_pages": (len(filtered_files) + limit - 1) // limit if limit > 0 else 0
            }
        }
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections", tags=["Search & Query"])
async def list_collections():
    """Lista tutte le collezioni disponibili"""
    try:
        if vector_store is None:
            raise HTTPException(status_code=503, detail="Vector store not initialized")
        
        collections = vector_store.list_collections()
        return {
            "collections": collections,
            "current_collection": vector_store.collection.name if hasattr(vector_store, 'collection') else None,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error listing collections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ====================== EMBEDDING ENDPOINTS ======================
@app.get("/embeddings/info", tags=["Embedding Operations"])
async def get_embedding_info():
    """Informazioni sull'embedder"""
    try:
        if embedder is None:
            raise HTTPException(status_code=503, detail="Embedder not initialized")
        
        info = embedder.get_model_info()
        
        # Aggiungi informazioni aggiuntive
        info.update({
            "device": getattr(embedder, 'device', 'unknown'),
            "max_batch_size": getattr(embedder, 'max_batch_size', 32),
            "normalize_embeddings": getattr(embedder, 'normalize_embeddings', False),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting embedding info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/embeddings/benchmark", tags=["Embedding Operations"])
async def run_embedding_benchmark(
    sample_size: int = Query(100, ge=10, le=1000),
    iterations: int = Query(3, ge=1, le=10),
    batch_size: int = Query(32, ge=1, le=256)
):
    """Esegue benchmark performance embedding"""
    try:
        if embedder is None:
            raise HTTPException(status_code=503, detail="Embedder not initialized")
        
        if EmbeddingBenchmark is None:
            raise HTTPException(status_code=503, detail="Embedding benchmark not available")
        
        # Usa il modello corrente per il benchmark
        model_name = getattr(embedder, 'model_name', 'sentence-transformers/all-MiniLM-L6-v2')
        
        sample_texts = [
            f"Sample document {i} for benchmarking semantic embedding performance with AI and machine learning applications. "
            f"This text contains various topics including natural language processing, computer vision, and deep learning."
            for i in range(sample_size)
        ]
        
        results = EmbeddingBenchmark.benchmark_model(
            model_name=model_name,
            test_texts=sample_texts,
            iterations=iterations,
            batch_size=batch_size
        )
        
        # Aggiungi raccomandazioni
        recommendations = []
        if results.get("avg_tokens_per_second", 0) < 1000:
            recommendations.append("Consider using GPU for better performance")
        if batch_size < 64 and getattr(embedder, 'device', '') == "cuda":
            recommendations.append("Increase batch_size for better GPU utilization")
        
        return {
            "benchmark_results": results,
            "parameters": {
                "sample_size": sample_size,
                "iterations": iterations,
                "batch_size": batch_size,
                "model": model_name
            },
            "recommendations": recommendations,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running embedding benchmark: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/embeddings/batch", tags=["Embedding Operations"])
async def generate_batch_embeddings(
    texts: List[str] = Form(...),
    normalize: bool = Form(False),
    batch_size: int = Form(32, ge=1, le=256)
):
    """Genera embeddings per batch di testi"""
    try:
        if embedder is None:
            raise HTTPException(status_code=503, detail="Embedder not initialized")
        
        if not texts:
            raise HTTPException(status_code=400, detail="Empty texts list")
        
        # Limita il numero di testi per evitare timeout
        max_texts = 1000
        if len(texts) > max_texts:
            texts = texts[:max_texts]
            logger.warning(f"Truncated texts list to {max_texts} items")
        
        logger.info(f"Generating embeddings for {len(texts)} texts, batch_size: {batch_size}")
        
        embeddings = embedder.embed_batch(texts, normalize=normalize, batch_size=batch_size)
        
        return {
            "embeddings_count": len(texts),
            "embedding_dimension": embeddings.shape[1] if len(embeddings.shape) > 1 else 1,
            "normalized": normalize,
            "sample_embedding": embeddings[0].tolist() if len(embeddings) > 0 else [],
            "processing_time_ms": "N/A",
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating batch embeddings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ====================== UTILITY ENDPOINTS ======================
@app.get("/api-spec", tags=["Utility"])
async def get_api_specification():
    """Restituisce specifica API OpenAPI"""
    try:
        # Genera lista automatica degli endpoint
        endpoints = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    endpoints.append({
                        "path": route.path,
                        "method": method,
                        "name": route.name if hasattr(route, "name") else "Unnamed"
                    })
        
        return {
            "endpoints": endpoints,
            "version": "2.0.0",
            "service": "Vector Ingestion Service",
            "timestamp": datetime.utcnow().isoformat(),
            "documentation": {
                "swagger": "/docs",
                "redoc": "/redoc",
                "openapi": "/openapi.json"
            }
        }
    except Exception as e:
        logger.error(f"Error getting API spec: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/config", tags=["Utility"])
async def get_configuration():
    """Restituisce la configurazione corrente"""
    return {
        "config": CONFIG,
        "environment": CONFIG["ENVIRONMENT"],
        "timestamp": datetime.utcnow().isoformat()
    }


@app.on_event("startup")
async def startup_event():
    """Evento all'avvio dell'app"""
    try:
        logger.info("=" * 60)
        logger.info("[START] Vector Ingestion Service Starting...")
        logger.info(f"[DATE] Start time: {app_start_time}")
        logger.info(f"[DIR] Static directory: {static_dir}")
        logger.info(f"[ENV] Environment: {CONFIG['ENVIRONMENT']}")
        
        # Log del path di Python per debug
        logger.info(f"[PYTHON] Python path: {sys.path}")
        
        # Verifica servizi
        services_status = {
            "Embedder": embedder is not None,
            "Vector Store": vector_store is not None,
            "DLQ": dlq is not None,
            "Document Processor": DocumentProcessor is not None
        }
        
        for service, status in services_status.items():
            status_icon = "[OK]" if status else "[FAIL]"
            logger.info(f"   {status_icon} {service}: {'Initialized' if status else 'Not available'}")

        await _ensure_pdf_ingest_runtime()
        
        logger.info("[READY] Service ready!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"🔥 Startup error: {e}")
        import traceback
        logger.error(traceback.format_exc())


# =============================================================================
# RAG MAGELLANO — Ralph 2-Tier Stratified RAG
# =============================================================================

@app.post("/rag/retrieve", tags=["RAG Magellano"])
async def rag_retrieve(
    request: Request,
    query: Optional[str] = Form(None, description="User query"),
    n_results: int = Form(RAG_DEFAULT_RETRIEVAL_CHUNKS, ge=1, le=RAG_MAX_RETRIEVAL_CHUNKS),
    min_similarity: float = Form(0.0, ge=0.0, le=1.0),
    source_filter: Optional[str] = Form(None),
    use_reranker: bool = Form(False),
):
    """
    Retrieval-only RAG entrypoint using the sentence-transformers MiniLM index.
    Useful for n8n and for Tier-0 operation while Magellano is offline.
    """
    payload = await _optional_json(request)
    query = _payload_value(payload, "query", query)
    n_results = _as_int(
        _payload_value(payload, "n_results", payload.get("top_k", n_results)),
        "n_results",
        1,
        RAG_MAX_RETRIEVAL_CHUNKS,
    )
    min_similarity = _as_float(
        _payload_value(payload, "min_similarity", min_similarity),
        "min_similarity",
        0.0,
        1.0,
    )
    source_filter = _payload_value(payload, "source_filter", payload.get("source", source_filter))
    use_reranker = _as_bool(_payload_value(payload, "use_reranker", use_reranker))

    if not query or not str(query).strip():
        raise HTTPException(status_code=400, detail="Empty query")

    vs = get_vector_store()
    if vs is None:
        raise HTTPException(status_code=503, detail="Vector store not available")

    retrieval_query = _rag_retrieval_query(str(query))
    where_filter = {"source": source_filter} if source_filter else None
    candidate_count = _rag_candidate_count(n_results)
    if use_reranker:
        candidate_results = vs.query_with_reranking(
            query_text=retrieval_query,
            n_results=candidate_count,
            where=where_filter,
            include_metadata=True,
            min_similarity=min_similarity,
        )
    else:
        candidate_results = vs.query(
            query_text=retrieval_query,
            n_results=candidate_count,
            where=where_filter,
            include_metadata=True,
            min_similarity=min_similarity,
        )

    candidate_results = _enrich_source_page_visuals(candidate_results)
    coherent_results = _rag_filter_coherent_results(str(query), retrieval_query, candidate_results)
    results = _rank_rag_results(
        str(query),
        retrieval_query,
        coherent_results,
        n_results,
    )

    return {
        "query": query,
        "retrieval_query": retrieval_query,
        "retrieval_count": len(results),
        "candidate_count": len(candidate_results),
        "coherent_candidate_count": len(coherent_results),
        "results": results,
        "retrieval_model": getattr(embedder, "model_name", "sentence-transformers/all-MiniLM-L6-v2"),
        "reranked": use_reranker,
        "filters": {
            "source": source_filter,
            "min_similarity": min_similarity,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/rag/query", tags=["RAG Magellano"])
async def rag_query(
    request: Request,
    query: Optional[str] = Form(None, description="User query"),
    n_results: int = Form(RAG_DEFAULT_RETRIEVAL_CHUNKS, ge=1, le=RAG_MAX_RETRIEVAL_CHUNKS, description="Max chunks to retrieve"),
    min_similarity: float = Form(0.0, ge=0.0, le=1.0, description="Minimum cosine similarity"),
    temperature: float = Form(0.7, ge=0.0, le=RAG_MAX_TEMPERATURE, description="Generation temperature"),
    max_tokens: int = Form(RAG_DEFAULT_MAX_TOKENS, ge=1, le=RAG_MAX_TOKENS, description="Max tokens for Magellano response"),
):
    """
    **Ralph 2-Tier Stratified RAG**

    - **Tier 0** (MiniLM-L6, ~20ms): dense retrieval from ChromaDB
    - **Tier 1** (Magellano 85k, ~800-1200ms): chain-of-thought generation

    If Magellano is unreachable the endpoint gracefully returns retrieval-only results.
    """
    payload = await _optional_json(request)
    query = _payload_value(payload, "query", query)
    n_results = _as_int(
        _payload_value(payload, "n_results", payload.get("top_k", n_results)),
        "n_results",
        1,
        RAG_MAX_RETRIEVAL_CHUNKS,
    )
    min_similarity = _as_float(
        _payload_value(payload, "min_similarity", min_similarity),
        "min_similarity",
        0.0,
        1.0,
    )
    temperature = _as_float(_payload_value(payload, "temperature", temperature), "temperature", 0.0, RAG_MAX_TEMPERATURE)
    max_tokens = _as_int(_payload_value(payload, "max_tokens", max_tokens), "max_tokens", 1, RAG_MAX_TOKENS)

    if not query or not str(query).strip():
        raise HTTPException(status_code=400, detail="Empty query")

    vs = get_vector_store()
    if vs is None:
        raise HTTPException(status_code=503, detail="Vector store not available")

    retrieval_query = _rag_retrieval_query(str(query))
    # ---------- Tier 0: Retrieval (MiniLM, fast) ----------
    try:
        candidate_results = _enrich_source_page_visuals(vs.query(
            query_text=retrieval_query,
            n_results=_rag_candidate_count(n_results),
            min_similarity=min_similarity,
        ))
        coherent_results = _rag_filter_coherent_results(str(query), retrieval_query, candidate_results)
        search_results = _rank_rag_results(str(query), retrieval_query, coherent_results, n_results)
    except Exception as e:
        logger.error(f"Retrieval error: {e}")
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {e}")

    if not search_results:
        return {
            "query": query,
            "answer": _rag_no_relevant_answer(str(query), retrieval_query),
            "sources": [],
            "citations": [],
            "retrieval_count": 0,
            "model": "none",
        }

    # ---------- Tier 1: Generation (Magellano 85k) ----------
    if get_magellano_client is None:
        # Library not installed — graceful degradation
        return {
            "query": query,
            "answer": _retrieval_fallback_answer(search_results),
            "sources": _result_sources(search_results),
            "citations": _public_chunk_refs(search_results),
            "retrieval_count": len(search_results),
            "model": "fallback-minilm-only",
            "warning": "MagellanoClient import failed",
        }

    magellano = get_magellano_client()
    health = await magellano.health()

    if not _magellano_ready(health.get("status")):
        # Service down — graceful degradation
        return {
            "query": query,
            "answer": _retrieval_fallback_answer(search_results),
            "sources": _result_sources(search_results),
            "citations": _public_chunk_refs(search_results),
            "retrieval_count": len(search_results),
            "model": "fallback-minilm-only",
            "warning": "Magellano unavailable",
            "magellano_health": health,
        }

    try:
        gen = await magellano.generate_rag_response(
            query=query,
            retrieved_chunks=_select_generation_context(str(query), retrieval_query, search_results),
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as e:
        # Health said "ready" but generation failed (timeout, restart, training window):
        # degrade to retrieval-only instead of failing the whole request.
        logger.error(f"Magellano generation error: {type(e).__name__}: {e}")
        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "answer": _retrieval_fallback_answer(search_results),
            "sources": _result_sources(search_results),
            "citations": _public_chunk_refs(search_results),
            "retrieval_count": len(search_results),
            "model": "fallback-minilm-only",
            "warning": f"Magellano generation failed: {type(e).__name__}",
        }

    return {
        "query": query,
        "retrieval_query": retrieval_query,
        "answer": gen.get("generated_text", ""),
        "sources": _result_sources(search_results),
        "citations": _public_chunk_refs(search_results),
        "retrieval_count": len(search_results),
        "tokens_used": gen.get("tokens_used"),
        "inference_time_ms": gen.get("processing_time_ms"),
        "model": gen.get("model", "magellano-85k"),
        "finish_reason": gen.get("finish_reason"),
        "magellano_endpoint": gen.get("endpoint"),
    }


@app.post("/rag/stream", tags=["RAG Magellano"])
async def rag_stream(
    request: Request,
    query: Optional[str] = Form(None, description="User query"),
    n_results: int = Form(RAG_DEFAULT_RETRIEVAL_CHUNKS, ge=1, le=RAG_MAX_RETRIEVAL_CHUNKS),
    temperature: float = Form(0.7, ge=0.0, le=RAG_MAX_TEMPERATURE),
    max_tokens: int = Form(RAG_DEFAULT_MAX_TOKENS, ge=64, le=RAG_MAX_TOKENS),
    min_similarity: float = Form(0.0, ge=0.0, le=1.0),
):
    """
    Tier-0 retrieval + Tier-2 Magellano streaming generation via SSE.

    Returns a text/event-stream with:
    - `data: {"type":"retrieval","count":N}` — retrieval summary
    - `data: {"type":"token","text":"..."}` — generated tokens
    - `data: [DONE]` — end of stream
    - `data: {"type":"error","message":"..."}` — on failure
    """
    payload = await _optional_json(request)
    query = _payload_value(payload, "query", query)
    n_results = _as_int(
        _payload_value(payload, "n_results", payload.get("top_k", n_results)),
        "n_results",
        1,
        RAG_MAX_RETRIEVAL_CHUNKS,
    )
    temperature = _as_float(_payload_value(payload, "temperature", temperature), "temperature", 0.0, RAG_MAX_TEMPERATURE)
    max_tokens = _as_int(_payload_value(payload, "max_tokens", max_tokens), "max_tokens", 1, RAG_MAX_TOKENS)
    min_similarity = _as_float(
        _payload_value(payload, "min_similarity", min_similarity),
        "min_similarity",
        0.0,
        1.0,
    )

    if not query or not str(query).strip():
        raise HTTPException(status_code=400, detail="Empty query")

    if not vector_store:
        raise HTTPException(status_code=503, detail="Vector store not available")

    retrieval_query = _rag_retrieval_query(str(query))
    # Tier-0: retrieve chunks
    try:
        candidate_results = _enrich_source_page_visuals(vector_store.query(
            query_text=retrieval_query,
            n_results=_rag_candidate_count(n_results),
            include_metadata=True,
            min_similarity=min_similarity,
        ))
        coherent_results = _rag_filter_coherent_results(str(query), retrieval_query, candidate_results)
        raw_results = _rank_rag_results(str(query), retrieval_query, coherent_results, n_results)
        context_results = _select_generation_context(str(query), retrieval_query, raw_results)
        chunk_texts = [r.get("content") or "" for r in raw_results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieval error: {e}")

    magellano = get_magellano_client() if get_magellano_client is not None else None

    async def event_generator():
        # Send retrieval summary
        retrieval_payload = {
            "type": "retrieval",
            "count": len(raw_results),
            "retrieval_query": retrieval_query,
            "context_count": len(context_results),
            "candidate_count": len(candidate_results),
            "coherent_candidate_count": len(coherent_results),
            "generation": {
                "max_tokens": max_tokens,
                "temperature": temperature,
                "context_budget_chunks": RAG_GENERATION_CONTEXT_CHUNKS,
            },
            "sources": _result_sources(raw_results),
            "chunks": _public_chunk_refs(raw_results),
            "context_chunks": _public_chunk_refs(context_results),
        }
        yield f"data: {json.dumps(retrieval_payload)}\n\n"

        if not chunk_texts:
            yield f"data: {json.dumps({'type': 'token', 'text': _rag_no_relevant_answer(str(query), retrieval_query)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        if magellano is None:
            yield f"data: {json.dumps({'type': 'token', 'text': _retrieval_fallback_answer(raw_results)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        health = await magellano.health()
        if not _magellano_ready(health.get("status")):
            yield f"data: {json.dumps({'type': 'token', 'text': _retrieval_fallback_answer(raw_results)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Stream Magellano tokens
        try:
            async for token in magellano.generate_rag_stream(
                query=query,
                chunks=chunk_texts,
                retrieved_chunks=context_results,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"
        except Exception as e:
            logger.error(f"RAG stream generation error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/rag/health", tags=["RAG Magellano"])
async def rag_health():
    """
    Returns combined health of the two-tier RAG stack:
    vector_store (Tier 0) + magellano (Tier 1).
    """
    vs_ok = get_vector_store() is not None

    if get_magellano_client is not None:
        magellano = get_magellano_client()
        mag_health = await magellano.health()
    else:
        mag_health = {"status": "not_configured"}

    return {
        "tier0_vector_store": "healthy" if vs_ok else "unavailable",
        "tier1_magellano": mag_health,
        "overall": "healthy" if (vs_ok and _magellano_ready(mag_health.get("status"))) else "degraded",
    }


@app.post("/embeddings/magellano", tags=["Embedding Operations"])
async def magellano_embeddings(
    texts: List[str] = Form(...),
    batch_size: int = Form(32, ge=1, le=64),
):
    """
    Generate embeddings using Magellano instead of MiniLM-L6.
    Useful for comparing embedding quality between the two models.
    """
    if get_magellano_client is None:
        raise HTTPException(status_code=503, detail="MagellanoClient not available")

    try:
        client = get_magellano_client()
        embeddings = await client.embed(texts, batch_size)
        return {
            "embeddings": embeddings.tolist(),
            "dimensions": int(embeddings.shape[1]) if embeddings.ndim == 2 else 0,
            "model": "magellano-85k-embed",
            "count": len(texts),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Magellano embed failed: {e}")


@app.post("/rag/multimodal", tags=["RAG Magellano"])
async def rag_multimodal(
    request: Request,
    file: UploadFile = File(...),
    query: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    include_text_context: bool = Form(True),
    n_results: int = Form(RAG_DEFAULT_RETRIEVAL_CHUNKS, ge=1, le=RAG_MAX_RETRIEVAL_CHUNKS),
    min_similarity: float = Form(0.0, ge=0.0, le=1.0),
    temperature: float = Form(0.2, ge=0.0, le=RAG_MAX_TEMPERATURE),
    max_tokens: int = Form(RAG_DEFAULT_MAX_TOKENS, ge=1, le=RAG_MAX_TOKENS),
):
    """
    Multimodal RAG preparation endpoint.

    Media intelligence is delegated to Magellano only.  MiniLM is used only for
    optional text-context retrieval, never for image/audio/video/table embeddings.
    """
    if get_magellano_client is None:
        raise HTTPException(status_code=503, detail="Magellano client not available")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    max_size = CONFIG["MAX_FILE_SIZE_MB"] * 1024 * 1024
    if len(contents) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (max {CONFIG['MAX_FILE_SIZE_MB']}MB)",
        )

    guessed_type = mimetypes.guess_type(file.filename)[0]
    media_type = file.content_type or guessed_type or "application/octet-stream"
    supported_prefixes = ("image/", "audio/", "video/")
    supported_table_types = {
        "text/csv",
        "text/plain",
        "text/tab-separated-values",
        "application/csv",
        "application/json",
        "application/pdf",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    if not media_type.startswith(supported_prefixes) and media_type not in supported_table_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported media type for Magellano multimodal RAG: {media_type}",
        )

    magellano = get_magellano_client()
    health = await magellano.health()
    if not _magellano_ready(health.get("status")):
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Magellano is required for multimodal RAG and is not ready",
                "magellano_health": health,
            },
        )

    text_context = []
    include_text_context = _as_bool(include_text_context)
    if include_text_context and query and vector_store:
        try:
            text_context = vector_store.query(
                query_text=query,
                n_results=n_results,
                include_metadata=True,
                min_similarity=min_similarity,
            )
        except Exception as e:
            logger.warning(f"Multimodal text-context retrieval failed: {e}")

    try:
        analysis = await magellano.analyze_media(
            file_content=contents,
            filename=file.filename,
            media_type=media_type,
            query=query,
            prompt=prompt,
            context_chunks=text_context,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as e:
        logger.error(f"Magellano multimodal analysis failed: {e}")
        raise HTTPException(status_code=502, detail=f"Magellano analysis failed: {e}")

    return {
        "query": query,
        "prompt": prompt,
        "filename": file.filename,
        "media_type": media_type,
        "file_size_bytes": len(contents),
        "analysis": analysis.get("analysis", ""),
        "model": analysis.get("model", "magellano-85k"),
        "magellano_endpoint": analysis.get("endpoint"),
        "processing_time_ms": analysis.get("processing_time_ms"),
        "text_context": {
            "enabled": include_text_context,
            "retrieval_count": len(text_context),
            "sources": _result_sources(text_context),
            "citations": _public_chunk_refs(text_context),
        },
        "raw": analysis.get("raw", {}),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/rag/adaptive", tags=["RAG Magellano"])
async def rag_adaptive(
    request: Request,
    query: Optional[str] = Form(None),
    n_results: int = Form(RAG_DEFAULT_RETRIEVAL_CHUNKS, ge=1, le=RAG_MAX_RETRIEVAL_CHUNKS),
    force_deep_reasoning: str = Form("auto", description='"auto" | "true" | "false"'),
    temperature: float = Form(0.7, ge=0.0, le=RAG_MAX_TEMPERATURE),
    min_similarity: float = Form(0.6, ge=0.0, le=1.0),
    max_tokens: int = Form(RAG_DEFAULT_MAX_TOKENS, ge=1, le=RAG_MAX_TOKENS),
):
    """
    **Adaptive RAG**: automatically routes the query to Tier 0 (fast retrieval)
    or Tier 1 (Magellano deep reasoning) based on query complexity heuristics.

    Complexity signals detected: conditional logic (se/qualora), boolean operators,
    quantifiers (sempre/mai), numeric thresholds, legal-consequence verbs.
    """
    import re

    payload = await _optional_json(request)
    query = _payload_value(payload, "query", query)
    n_results = _as_int(
        _payload_value(payload, "n_results", payload.get("top_k", n_results)),
        "n_results",
        1,
        RAG_MAX_RETRIEVAL_CHUNKS,
    )
    force_deep_reasoning = str(_payload_value(payload, "force_deep_reasoning", force_deep_reasoning)).lower()
    temperature = _as_float(_payload_value(payload, "temperature", temperature), "temperature", 0.0, RAG_MAX_TEMPERATURE)
    min_similarity = _as_float(
        _payload_value(payload, "min_similarity", min_similarity),
        "min_similarity",
        0.0,
        1.0,
    )
    max_tokens = _as_int(_payload_value(payload, "max_tokens", max_tokens), "max_tokens", 1, RAG_MAX_TOKENS)

    if not query or not str(query).strip():
        raise HTTPException(status_code=400, detail="Empty query")

    # ---- Complexity heuristics ----
    complex_patterns = [
        r'\b(se|qualora|nel\s+caso)\b',
        r'\b(e|oppure)\b.*\b(son[oi]|è)\b',
        r'\b(sempre|mai|solo\s+se)\b',
        r'\d+\s*(km/h|anni|mesi|cicli)',
        r'\b(invalida|perde|decade|annulla)\b',
    ]
    complexity_score = sum(
        1 for p in complex_patterns if re.search(p, query, re.IGNORECASE)
    )

    if force_deep_reasoning == "true":
        use_tier1 = True
        routing_reason = "forced_by_user"
    elif force_deep_reasoning == "false":
        use_tier1 = False
        routing_reason = "forced_tier0_only"
    else:
        use_tier1 = complexity_score >= 2 or len(query) > 80
        routing_reason = f"complexity_score_{complexity_score}"

    if use_tier1:
        result = await rag_query(
            request=request,
            query=query,
            n_results=n_results,
            min_similarity=min_similarity,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        result["routing_decision"] = f"tier1_deep_reasoning ({routing_reason})"
        result["complexity_score"] = complexity_score
        return result
    else:
        vs = get_vector_store()
        if vs is None:
            raise HTTPException(status_code=503, detail="Vector store not available")
        results = vs.query(
            query_text=query,
            n_results=n_results,
            include_metadata=True,
            min_similarity=min_similarity,
        )
        return {
            "query": query,
            "answer": "Risultati trovati: " + "; ".join(r["content"][:100] for r in results[:3]),
            "sources": _result_sources(results),
            "citations": _public_chunk_refs(results),
            "retrieval_count": len(results),
            "routing_decision": f"tier0_fast_retrieval ({routing_reason})",
            "complexity_score": complexity_score,
            "model": "minilm-l6-only",
        }


# =============================================================================

@app.on_event("shutdown")
async def shutdown_event():
    """Evento allo spegnimento dell'app"""
    logger.info("👋 Shutting down Vector Ingestion Service...")
    try:
        await _stop_pdf_ingest_workers()
        # Pulizia risorse se necessario
        if vector_store:
            logger.info("Cleaning up vector store connections...")
        # Close Magellano async HTTP client
        if get_magellano_client is not None:
            try:
                await get_magellano_client().close()
                logger.info("MagellanoClient closed")
            except Exception:
                pass
        logger.info("Goodbye!")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


if __name__ == "__main__":
    import uvicorn
    
    # Configurazione uvicorn
    config = {
        "host": os.environ.get("HOST", "0.0.0.0"),
        "port": int(os.environ.get("PORT", 8000)),
        "reload": os.environ.get("RELOAD", "false").lower() == "true",
        "log_level": os.environ.get("LOG_LEVEL", "info"),
        "workers": int(os.environ.get("WORKERS", 1))
    }
    
    logger.info(f"Starting server on {config['host']}:{config['port']}")
    logger.info(f"Reload: {config['reload']}, Log level: {config['log_level']}, Workers: {config['workers']}")
    
    uvicorn.run(
        "main:app",
        host=config["host"],
        port=config["port"],
        reload=config["reload"],
        log_level=config["log_level"],
        workers=config["workers"]
    )
