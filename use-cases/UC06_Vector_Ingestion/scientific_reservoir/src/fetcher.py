#!/usr/bin/env python3
"""
scientific_reservoir/src/fetcher.py
====================================
Fetcher enterprise per serbatoio scientifico locale.
Alimenta il Vector Ingestion Service (port 8003) e il Magellano RAG 2-Tier.

Modalità:
  --standalone   Salva documenti su filesystem (JSON + testo) senza servizi.
  (default)      Integrata: posta su /upload/text del Vector Service.

Comandi CLI:
  python fetcher.py fetch   [--sources arxiv semantic_scholar kdnuggets openreview paperswithcode]
                             [--days N] [--max N] [--standalone] [--vector-url URL]
  python fetcher.py ingest  [--batch-size N] [--vector-url URL] [--magellano-url URL]
  python fetcher.py stats
  python fetcher.py full    [stesse opzioni di fetch + ingest]

Variabili d'ambiente:
  SCIENTIFIC_RESERVOIR   Path root serbatoio  (default ./scientific_reservoir)
  VECTOR_SERVICE_URL     URL Vector Service   (default http://localhost:8003)
  MAGELLANO_SERVICE_URL  URL Magellano API    (default http://localhost:8004)
  S2_API_KEY             Semantic Scholar API key (opzionale)
"""

import os
import sys
import json
import yaml
import asyncio
import aiohttp
import hashlib
import sqlite3
import textwrap
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple
import logging

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("reservoir")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ENV_ROOT = os.getenv("SCIENTIFIC_RESERVOIR", str(Path(__file__).parent.parent))
BASE_DIR      = Path(_ENV_ROOT)
QUEUE_DIR     = BASE_DIR / "00_queue"
INGESTING_DIR = BASE_DIR / "01_ingesting"
RESERVOIR_DIR = BASE_DIR / "02_reservoir"
EMBEDDINGS_DIR= BASE_DIR / "03_embeddings"
FAILED_DIR    = BASE_DIR / "04_failed"
CONFIG_DIR    = BASE_DIR / "config"
DB_PATH       = BASE_DIR / "reservoir.db"

_DEFAULT_VECTOR_URL    = os.getenv("VECTOR_SERVICE_URL",   "http://localhost:8003")
_DEFAULT_MAGELLANO_URL = os.getenv("MAGELLANO_SERVICE_URL","http://localhost:8004")


# ===========================================================================
# Data model
# ===========================================================================

@dataclass
class ScientificDocument:
    """Modello unificato documento scientifico."""
    reservoir_id:  str
    source:        str
    external_id:   str
    title:         str
    authors:       List[str]
    abstract:      str
    full_text:     Optional[str]   = None
    pdf_url:       Optional[str]   = None
    html_url:      Optional[str]   = None
    year:          int             = 0
    venue:         str             = ""
    doi:           Optional[str]   = None
    citation_count:int             = 0
    reference_count:int            = 0
    domains:       List[str]       = field(default_factory=list)
    keywords:      List[str]       = field(default_factory=list)
    relevance_score:float          = 0.0
    fetched_at:    Optional[datetime] = None
    processed_at:  Optional[datetime] = None
    ingested_at:   Optional[datetime] = None
    embedding_cached: bool         = False
    pdf_path:      Optional[Path]  = None
    meta_path:     Optional[Path]  = None

    def __post_init__(self):
        if self.fetched_at is None:
            self.fetched_at = datetime.now()

    def generate_reservoir_id(self) -> str:
        content = f"{self.source}:{self.external_id}:{self.title}"
        h = hashlib.sha256(content.encode()).hexdigest()[:16]
        return f"{self.source}_{self.year}_{h}"

    def to_dict(self) -> Dict:
        d = asdict(self)
        for key in ("fetched_at", "processed_at", "ingested_at"):
            v = d.get(key)
            d[key] = v.isoformat() if isinstance(v, datetime) else v
        d["pdf_path"]  = str(self.pdf_path)  if self.pdf_path  else None
        d["meta_path"] = str(self.meta_path) if self.meta_path else None
        return d

    def to_ingestion_text(self) -> str:
        """
        Genera il testo da inviare a /upload/text.
        Embedda titolo, autori, venue e abstract in un blocco leggibile
        che il chunker può elaborare senza metadata separati.
        """
        lines = [
            f"TITLE: {self.title}",
            f"AUTHORS: {', '.join(self.authors)}",
            f"YEAR: {self.year}",
            f"VENUE: {self.venue}",
            f"SOURCE: {self.source}",
            f"DOMAINS: {', '.join(self.domains)}",
            f"RELEVANCE_SCORE: {self.relevance_score:.2f}",
            f"CITATION_COUNT: {self.citation_count}",
            "",
            "ABSTRACT:",
            self.abstract or "",
        ]
        if self.full_text:
            lines += ["", "FULL_TEXT:", self.full_text[:100_000]]
        return "\n".join(lines)


# ===========================================================================
# Database
# ===========================================================================

class ReservoirDatabase:
    """SQLite per tracking, deduplicazione e coda di ingestion."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    reservoir_id    TEXT PRIMARY KEY,
                    source          TEXT NOT NULL,
                    external_id     TEXT NOT NULL,
                    title           TEXT NOT NULL,
                    authors         TEXT,
                    abstract        TEXT,
                    full_text       TEXT,
                    year            INTEGER,
                    venue           TEXT,
                    doi             TEXT,
                    citation_count  INTEGER DEFAULT 0,
                    domains         TEXT,
                    keywords        TEXT,
                    relevance_score REAL DEFAULT 0,
                    pdf_path        TEXT,
                    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at    TIMESTAMP,
                    ingested_at     TIMESTAMP,
                    embedding_cached BOOLEAN DEFAULT 0,
                    UNIQUE(source, external_id)
                );
                CREATE INDEX IF NOT EXISTS idx_source    ON documents(source);
                CREATE INDEX IF NOT EXISTS idx_year      ON documents(year);
                CREATE INDEX IF NOT EXISTS idx_relevance ON documents(relevance_score);
                CREATE INDEX IF NOT EXISTS idx_fetched   ON documents(fetched_at);

                CREATE TABLE IF NOT EXISTS fetch_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    source          TEXT NOT NULL,
                    query           TEXT,
                    items_found     INTEGER,
                    items_new       INTEGER,
                    items_duplicate INTEGER,
                    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS ingestion_queue (
                    reservoir_id TEXT PRIMARY KEY,
                    priority     INTEGER DEFAULT 5,
                    attempts     INTEGER DEFAULT 0,
                    last_error   TEXT,
                    status       TEXT DEFAULT 'pending',
                    FOREIGN KEY (reservoir_id) REFERENCES documents(reservoir_id)
                );
            """)

    # ------------------------------------------------------------------
    def exists(self, source: str, external_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT 1 FROM documents WHERE source=? AND external_id=?",
                (source, external_id),
            )
            return cur.fetchone() is not None

    def insert(self, doc: ScientificDocument) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """INSERT INTO documents
                       (reservoir_id, source, external_id, title, authors, abstract,
                        year, venue, doi, citation_count, domains, keywords,
                        relevance_score, pdf_path, fetched_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        doc.reservoir_id,
                        doc.source,
                        doc.external_id,
                        doc.title,
                        json.dumps(doc.authors),
                        doc.abstract,
                        doc.year,
                        doc.venue,
                        doc.doi,
                        doc.citation_count,
                        json.dumps(doc.domains),
                        json.dumps(doc.keywords),
                        doc.relevance_score,
                        str(doc.pdf_path) if doc.pdf_path else None,
                        doc.fetched_at,
                    ),
                )
                priority = min(10, max(1, int(doc.relevance_score * 2)))
                conn.execute(
                    "INSERT OR IGNORE INTO ingestion_queue (reservoir_id, priority) VALUES (?,?)",
                    (doc.reservoir_id, priority),
                )
                return True
        except sqlite3.IntegrityError:
            return False

    def get_pending_ingestion(self, limit: int = 100) -> List[Dict]:
        """Restituisce dicts con tutti i campi necessari per ingestion."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                """SELECT d.*, q.priority, q.attempts
                   FROM documents d
                   JOIN ingestion_queue q ON d.reservoir_id = q.reservoir_id
                   WHERE q.status = 'pending'
                   ORDER BY q.priority DESC, q.attempts ASC
                   LIMIT ?""",
                (limit,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def mark_ingested(self, reservoir_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE documents SET ingested_at=? WHERE reservoir_id=?",
                (datetime.now(), reservoir_id),
            )
            conn.execute(
                "UPDATE ingestion_queue SET status='done' WHERE reservoir_id=?",
                (reservoir_id,),
            )

    def mark_ingestion_failed(self, reservoir_id: str, error: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE ingestion_queue
                   SET attempts=attempts+1, last_error=?, status=CASE WHEN attempts+1>=3 THEN 'failed' ELSE 'pending' END
                   WHERE reservoir_id=?""",
                (error[:500], reservoir_id),
            )

    def log_fetch(self, source: str, query: str, found: int, new: int, dup: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO fetch_log (source, query, items_found, items_new, items_duplicate) VALUES (?,?,?,?,?)",
                (source, query, found, new, dup),
            )

    def stats(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT source,
                          COUNT(*) as total,
                          SUM(CASE WHEN ingested_at IS NOT NULL THEN 1 ELSE 0 END) as ingested,
                          ROUND(AVG(relevance_score),2) as avg_relevance
                   FROM documents GROUP BY source"""
            ).fetchall()
            pending = conn.execute(
                "SELECT COUNT(*) FROM ingestion_queue WHERE status='pending'"
            ).fetchone()[0]
        return {
            "by_source": [
                {"source": r[0], "total": r[1], "ingested": r[2], "avg_relevance": r[3]}
                for r in rows
            ],
            "pending_ingestion": pending,
        }


# ===========================================================================
# Keyword Classifier
# ===========================================================================

class KeywordClassifier:
    """Classificatore documenti basato su ontologia YAML."""

    def __init__(self, config_path: Path = CONFIG_DIR / "keywords.yml"):
        with open(config_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.weights = self.config.get("relevance_weights", {})
        self.domain_patterns = self._compile_patterns()

    def _compile_patterns(self) -> Dict[str, List[Tuple[str, float]]]:
        def _add(pats: list, value, weight: float):
            """Aggiunge keyword da lista piatta o da dict {categoria: [kw,...]}."""
            if isinstance(value, list):
                for kw in value:
                    if isinstance(kw, str):
                        pats.append((kw.lower(), weight))
            elif isinstance(value, dict):
                for items in value.values():
                    if isinstance(items, list):
                        for kw in items:
                            if isinstance(kw, str):
                                pats.append((kw.lower(), weight))

        patterns: Dict[str, List[Tuple[str, float]]] = {}
        for domain, cfg in self.config["domains"].items():
            pats: List[Tuple[str, float]] = []
            _add(pats, cfg.get("primary",              []), 2.5)
            _add(pats, cfg.get("innovations",          []), 2.0)
            _add(pats, cfg.get("subdomains",           {}), 2.0)
            _add(pats, cfg.get("tools",                {}), 1.5)
            _add(pats, cfg.get("frameworks",           {}), 1.5)
            _add(pats, cfg.get("techniques",           {}), 1.5)
            _add(pats, cfg.get("engineering_patterns", []), 1.5)
            _add(pats, cfg.get("infrastructure",       []), 1.5)
            _add(pats, cfg.get("monitoring",           []), 1.5)
            _add(pats, cfg.get("algorithms",           []), 1.5)
            _add(pats, cfg.get("hybrid_systems",       []), 1.5)
            _add(pats, cfg.get("safety_standards",     []), 1.5)
            _add(pats, cfg.get("domains",              []), 1.5)
            _add(pats, cfg.get("patterns",             []), 1.5)
            patterns[domain] = pats
        return patterns

    def classify(
        self,
        title: str,
        abstract: str,
        extra_keywords: Optional[List[str]] = None,
    ) -> Tuple[List[str], float]:
        title_l    = (title or "").lower()
        abstract_l = (abstract or "").lower()
        kw_text    = " ".join(extra_keywords).lower() if extra_keywords else ""
        tw = self.weights.get("title_match",    3.5)
        aw = self.weights.get("abstract_match", 2.0)
        kw = self.weights.get("keyword_match",  2.5)

        domain_scores: Dict[str, float] = {}
        for domain, pats in self.domain_patterns.items():
            score = 0.0
            for pat, weight in pats:
                if pat in title_l:
                    score += weight * tw
                elif pat in abstract_l:
                    score += weight * aw
                elif kw_text and pat in kw_text:
                    score += weight * kw
            if score > 0:
                domain_scores[domain] = score

        threshold = 2.0
        selected = [
            d for d, s in sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
            if s >= threshold
        ][:3]
        return selected, sum(domain_scores.values())


# ===========================================================================
# Standalone file writer
# ===========================================================================

def save_standalone(doc: ScientificDocument):
    """Salva documento su filesystem senza richiedere servizi attivi."""
    source_dir = RESERVOIR_DIR / "by_source" / doc.source
    source_dir.mkdir(parents=True, exist_ok=True)

    meta_path = source_dir / f"{doc.reservoir_id}.json"
    text_path = source_dir / f"{doc.reservoir_id}.txt"

    meta_path.write_text(json.dumps(doc.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    text_path.write_text(doc.to_ingestion_text(), encoding="utf-8")

    # Indice per dominio
    for domain in doc.domains:
        domain_dir = RESERVOIR_DIR / "by_domain" / domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        symlink = domain_dir / f"{doc.reservoir_id}.txt"
        if not symlink.exists():
            try:
                symlink.symlink_to(text_path)
            except (OSError, NotImplementedError):
                pass  # symlink non supportato su alcuni FS Windows


# ===========================================================================
# Magellano Bridge
# ===========================================================================

class MagellanoBridge:
    """
    Bridge asincrono verso Vector Service (porta 8003) e Magellano API (porta 8004).
    Supporta ingestion di documenti con o senza PDF.
    """

    def __init__(
        self,
        vector_url:    str = _DEFAULT_VECTOR_URL,
        magellano_url: str = _DEFAULT_MAGELLANO_URL,
    ):
        self.vector_url    = vector_url.rstrip("/")
        self.magellano_url = magellano_url.rstrip("/")
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def health_check(self) -> Tuple[bool, bool]:
        """Ritorna (vector_ok, magellano_ok)."""
        async def check(url: str) -> bool:
            try:
                async with self.session.get(f"{url}/health", timeout=aiohttp.ClientTimeout(total=5)) as r:
                    return r.status == 200
            except Exception:
                return False

        v, m = await asyncio.gather(
            check(self.vector_url),
            check(self.magellano_url),
        )
        return v, m

    async def ingest_document(self, doc: ScientificDocument) -> bool:
        """
        Ingestisce il documento nel Vector Service tramite /upload/text.
        Usa full_text se disponibile, altrimenti abstract.
        Compatibile con il contratto Form dell'endpoint FastAPI.
        """
        text = doc.to_ingestion_text()
        if not text.strip():
            logger.warning(f"Documento vuoto, skip: {doc.reservoir_id}")
            return False

        form_data = aiohttp.FormData()
        form_data.add_field("content",       text)
        form_data.add_field("source_id",     doc.reservoir_id)
        form_data.add_field("chunk_size",    "1000")
        form_data.add_field("chunk_overlap", "150")

        try:
            async with self.session.post(
                f"{self.vector_url}/upload/text",
                data=form_data,
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    logger.info(
                        f"Ingested {doc.reservoir_id}: "
                        f"{result.get('chunks_processed', '?')} chunks"
                    )
                    return True
                body = await resp.text()
                logger.error(f"Ingestion failed ({resp.status}): {body[:200]}")
                return False
        except Exception as e:
            logger.error(f"Connection error for {doc.reservoir_id}: {e}")
            return False

    async def cache_magellano_embedding(self, doc: ScientificDocument) -> bool:
        """Pre-calcola embedding Magellano per retrieval veloce (facoltativo)."""
        text = f"{doc.title}. {doc.abstract}"
        try:
            async with self.session.post(
                f"{self.magellano_url}/embed",
                json={"texts": [text], "batch_size": 1},
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    emb = result.get("embeddings", [[]])[0]
                    emb_path = EMBEDDINGS_DIR / f"{doc.reservoir_id}.json"
                    emb_path.write_text(json.dumps(emb), encoding="utf-8")
                    return True
        except Exception as e:
            logger.warning(f"Magellano embedding failed for {doc.reservoir_id}: {e}")
        return False


# ===========================================================================
# Fetchers
# ===========================================================================

class ArxivFetcher:
    # RSS feeds per categoria — endpoint separato dall'export API, nessun rate-limit IP-level
    RSS_BASE   = "https://rss.arxiv.org/rss/{cat}"
    # API export come fallback (bloccata più facilmente)
    API_BASE   = "http://export.arxiv.org/api/query"
    CATEGORIES = [
        "cs.AI","cs.LG","cs.CL","cs.CV","cs.RO","cs.SE",
        "cs.CR","cs.DB","cs.DC","cs.DS",
        "stat.ML",
    ]

    def __init__(self, db: ReservoirDatabase, classifier: KeywordClassifier):
        self.db         = db
        self.classifier = classifier
        self._sem       = asyncio.Semaphore(1)   # 1 richiesta alla volta per arXiv

    async def fetch_recent(
        self,
        days: int = 7,
        max_results: int = 500,
    ) -> Dict:
        try:
            import feedparser
        except ImportError:
            logger.error("feedparser non installato. pip install feedparser")
            return {"source": "arxiv", "found": 0, "new": 0, "duplicates": 0, "documents": []}

        logger.info(f"arXiv RSS: {len(self.CATEGORIES)} categorie, max {max_results} totali")
        docs, new_cnt, dup_cnt = [], 0, 0
        cutoff = datetime.now() - timedelta(days=days)
        per_cat = max(10, max_results // len(self.CATEGORIES))

        for i, cat in enumerate(self.CATEGORIES):
            if len(docs) >= max_results:
                break
            if i > 0:
                await asyncio.sleep(1.0)   # rispetta cortesia verso arXiv RSS

            rss_url = self.RSS_BASE.format(cat=cat)
            try:
                feed = feedparser.parse(rss_url)
            except Exception as exc:
                logger.warning(f"arXiv RSS {cat}: errore parse — {exc}")
                continue

            if not feed.entries:
                logger.debug(f"arXiv RSS {cat}: nessun entry")
                continue

            cat_new = 0
            for entry in feed.entries[:per_cat]:
                if len(docs) >= max_results:
                    break
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                if published:
                    pub_date = datetime(*published[:6])
                    if pub_date < cutoff:
                        continue
                else:
                    pub_date = datetime.now()

                # RSS id = "oai:arXiv.org:2604.00005v1" — usare link che ha formato URL
                link = entry.get("link") or entry.get("id", "")
                arxiv_id = link.split("/abs/")[-1].split("v")[0].strip()
                if not arxiv_id or "/" in arxiv_id:
                    continue
                if self.db.exists("arxiv", arxiv_id):
                    dup_cnt += 1
                    continue

                authors = [a.get("name", "") for a in entry.get("authors", [])]
                title   = entry.get("title", "").replace("\n", " ").strip()
                abstract = entry.get("summary", "").replace("\n", " ").strip()

                domains, relevance = self.classifier.classify(title, abstract)
                if relevance < 2.0:
                    continue

                doc = ScientificDocument(
                    reservoir_id="",
                    source="arxiv",
                    external_id=arxiv_id,
                    title=title,
                    authors=authors,
                    abstract=abstract[:2000],
                    year=pub_date.year,
                    venue=f"arXiv:{cat}",
                    pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
                    html_url=f"https://arxiv.org/abs/{arxiv_id}",
                    domains=domains,
                    keywords=[cat],
                    relevance_score=relevance,
                )
                doc.reservoir_id = doc.generate_reservoir_id()
                docs.append(doc)
                if self.db.insert(doc):
                    new_cnt += 1
                    cat_new += 1

            logger.debug(f"arXiv RSS {cat}: {cat_new} nuovi")

        self.db.log_fetch("arxiv", "RSS feeds", len(docs) + dup_cnt, new_cnt, dup_cnt)
        logger.info(f"arXiv: {len(docs) + dup_cnt} trovati, {new_cnt} nuovi, {dup_cnt} duplicati")
        return {"source": "arxiv", "found": len(docs) + dup_cnt, "new": new_cnt, "duplicates": dup_cnt, "documents": docs}

        feed = feedparser.parse(raw)
        docs, new_cnt, dup_cnt = [], 0, 0

        for entry in feed.entries:
            arxiv_id = entry.id.split("/abs/")[-1].split("v")[0]
            if self.db.exists("arxiv", arxiv_id):
                dup_cnt += 1
                continue

            authors    = [a.name for a in entry.get("authors", [])]
            categories = [t.term for t in entry.get("tags", [])]
            domains, relevance = self.classifier.classify(entry.title, entry.summary, categories)

            if relevance < 3.0:
                continue

            pdf_url = next(
                (lk.href for lk in entry.links if lk.type == "application/pdf"), None
            )
            doc = ScientificDocument(
                reservoir_id="",
                source="arxiv",
                external_id=arxiv_id,
                title=entry.title,
                authors=authors,
                abstract=entry.summary,
                year=int(entry.published[:4]),
                venue="arXiv " + ", ".join(categories[:2]),
                pdf_url=pdf_url,
                html_url=entry.id,
                domains=domains,
                keywords=categories,
                relevance_score=relevance,
            )
            doc.reservoir_id = doc.generate_reservoir_id()
            docs.append(doc)
            if self.db.insert(doc):
                new_cnt += 1

        self.db.log_fetch("arxiv", query, len(feed.entries), new_cnt, dup_cnt)
        logger.info(f"arXiv: {len(feed.entries)} trovati, {new_cnt} nuovi, {dup_cnt} duplicati")
        return {"source": "arxiv", "found": len(feed.entries), "new": new_cnt, "duplicates": dup_cnt, "documents": docs}


class SemanticScholarFetcher:
    API_BASE = "https://api.semanticscholar.org/graph/v1"

    def __init__(
        self,
        db: ReservoirDatabase,
        classifier: KeywordClassifier,
        api_key: Optional[str] = None,
    ):
        self.db         = db
        self.classifier = classifier
        self.api_key    = api_key
        self._sem       = asyncio.Semaphore(2)

    async def search_by_keywords(self, keywords: List[str], limit: int = 50) -> Dict:
        query  = " ".join(keywords)
        params = {
            "query": query,
            "fields": "paperId,title,abstract,year,authors,venue,citationCount,"
                      "referenceCount,openAccessPdf,fieldsOfStudy",
            "limit": limit,
        }
        headers = {"x-api-key": self.api_key} if self.api_key else {}

        data = None
        async with aiohttp.ClientSession() as session:
            async with self._sem:
                for attempt in range(4):
                    async with session.get(
                        f"{self.API_BASE}/paper/search", params=params, headers=headers
                    ) as resp:
                        if resp.status == 429:
                            wait = 2 ** attempt
                            logger.warning(f"S2 rate limit (429), retry in {wait}s (attempt {attempt+1}/4)...")
                            await asyncio.sleep(wait)
                            continue
                        if resp.status != 200:
                            logger.error(f"S2 API error {resp.status}")
                            return {"source": "semantic_scholar", "found": 0, "new": 0, "duplicates": 0, "documents": []}
                        data = await resp.json()
                        break
        if data is None:
            logger.error("S2 API: tutti i retry esauriti (429 persistente)")
            return {"source": "semantic_scholar", "found": 0, "new": 0, "duplicates": 0, "documents": []}

        docs, new_cnt, dup_cnt = [], 0, 0
        for paper in data.get("data", []):
            pid = paper.get("paperId")
            if self.db.exists("semantic_scholar", pid):
                dup_cnt += 1
                continue

            authors = [a.get("name") for a in paper.get("authors", [])]
            fields  = paper.get("fieldsOfStudy") or []
            domains, relevance = self.classifier.classify(
                paper.get("title", ""), paper.get("abstract", ""), fields
            )
            if relevance < 3.0:
                continue

            citation_boost = paper.get("citationCount", 0) / 1000
            doc = ScientificDocument(
                reservoir_id="",
                source="semantic_scholar",
                external_id=pid,
                title=paper.get("title", ""),
                authors=authors,
                abstract=paper.get("abstract", ""),
                year=paper.get("year", 0),
                venue=paper.get("venue", ""),
                citation_count=paper.get("citationCount", 0),
                reference_count=paper.get("referenceCount", 0),
                pdf_url=(paper.get("openAccessPdf") or {}).get("url"),
                domains=domains,
                keywords=fields,
                relevance_score=relevance + citation_boost,
            )
            doc.reservoir_id = doc.generate_reservoir_id()
            docs.append(doc)
            if self.db.insert(doc):
                new_cnt += 1

        self.db.log_fetch("semantic_scholar", query, len(data.get("data", [])), new_cnt, dup_cnt)
        return {"source": "semantic_scholar", "found": len(data.get("data", [])), "new": new_cnt, "duplicates": dup_cnt, "documents": docs}


class KDnuggetsFetcher:
    RSS_FEEDS = ["https://www.kdnuggets.com/feed"]

    def __init__(self, db: ReservoirDatabase, classifier: KeywordClassifier):
        self.db         = db
        self.classifier = classifier

    async def fetch_articles(self, max_age_days: int = 14) -> Dict:
        try:
            import feedparser
        except ImportError:
            logger.error("feedparser non installato.")
            return {"source": "kdnuggets", "found": 0, "new": 0, "duplicates": 0, "documents": []}

        logger.info(f"KDnuggets: ultimi {max_age_days} giorni")
        docs, new_cnt, dup_cnt = [], 0, 0
        cutoff = datetime.now() - timedelta(days=max_age_days)

        for feed_url in self.RSS_FEEDS:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                published = entry.get("published_parsed")
                if published:
                    pub_date = datetime(*published[:6])
                    if pub_date < cutoff:
                        continue
                else:
                    pub_date = datetime.now()

                import hashlib as _hl
                article_id = _hl.md5(entry.link.encode()).hexdigest()[:16]
                if self.db.exists("kdnuggets", article_id):
                    dup_cnt += 1
                    continue

                categories = [t.term for t in entry.get("tags", [])]
                domains, relevance = self.classifier.classify(
                    entry.title, entry.get("summary", ""), categories
                )
                if not domains:
                    continue

                doc = ScientificDocument(
                    reservoir_id="",
                    source="kdnuggets",
                    external_id=article_id,
                    title=entry.title,
                    authors=[entry.get("author", "KDnuggets")],
                    abstract=entry.get("summary", "")[:1000],
                    year=pub_date.year,
                    venue="KDnuggets",
                    html_url=entry.link,
                    domains=domains,
                    keywords=categories,
                    relevance_score=relevance * 0.9,
                )
                doc.reservoir_id = doc.generate_reservoir_id()
                docs.append(doc)
                if self.db.insert(doc):
                    new_cnt += 1   # FIX: era new_cnt += 0

        self.db.log_fetch("kdnuggets", "RSS feeds", len(docs) + dup_cnt, new_cnt, dup_cnt)
        logger.info(f"KDnuggets: {len(docs) + dup_cnt} trovati, {new_cnt} nuovi, {dup_cnt} duplicati")
        return {"source": "kdnuggets", "found": len(docs) + dup_cnt, "new": new_cnt, "duplicates": dup_cnt, "documents": docs}


class PapersWithCodeFetcher:
    API_BASE = "https://paperswithcode.com/api/v1"

    def __init__(self, db: ReservoirDatabase, classifier: KeywordClassifier):
        self.db         = db
        self.classifier = classifier

    async def fetch_sota_papers(
        self, areas: Optional[List[str]] = None, limit: int = 50
    ) -> Dict:
        areas = areas or ["machine-learning", "natural-language-processing", "computer-vision"]
        logger.info(f"PapersWithCode: SOTA per {areas}")
        all_docs, new_cnt = [], 0

        async with aiohttp.ClientSession() as session:
            for area in areas:
                try:
                    async with session.get(
                        f"{self.API_BASE}/areas/{area}/tasks/", params={"limit": 20}
                    ) as resp:
                        tasks = await resp.json()
                except Exception as e:
                    logger.warning(f"PwC area {area} error: {e}")
                    continue

                for task in tasks.get("results", [])[:5]:
                    task_slug = task.get("name", "")
                    try:
                        async with session.get(
                            f"{self.API_BASE}/tasks/{task_slug}/papers/",
                            params={"ordering": "-published", "limit": limit // len(areas)},
                        ) as resp:
                            papers = await resp.json()
                    except Exception as e:
                        logger.warning(f"PwC task {task_slug} error: {e}")
                        continue

                    for paper in papers.get("results", []):
                        pid = f"pwc_{paper['id']}"
                        if self.db.exists("paperswithcode", pid):
                            continue
                        domains, relevance = self.classifier.classify(
                            paper["title"], paper.get("abstract", "")
                        )
                        year = 0
                        if paper.get("published"):
                            try:
                                year = int(paper["published"][:4])
                            except ValueError:
                                pass
                        doc = ScientificDocument(
                            reservoir_id="",
                            source="paperswithcode",
                            external_id=pid,
                            title=paper["title"],
                            authors=[],
                            abstract=paper.get("abstract", ""),
                            year=year,
                            venue=task_slug,
                            pdf_url=paper.get("url_pdf"),
                            html_url=paper.get("url_abs"),
                            domains=domains,
                            keywords=[task_slug],
                            relevance_score=relevance + 0.5,
                        )
                        doc.reservoir_id = doc.generate_reservoir_id()
                        all_docs.append(doc)
                        if self.db.insert(doc):
                            new_cnt += 1

        logger.info(f"PapersWithCode: {len(all_docs)} trovati, {new_cnt} nuovi")
        return {"source": "paperswithcode", "found": len(all_docs), "new": new_cnt, "documents": all_docs}


class OpenReviewFetcher:
    API_BASE = "https://api.openreview.net"

    def __init__(self, db: ReservoirDatabase, classifier: KeywordClassifier):
        self.db         = db
        self.classifier = classifier

    async def fetch_conference(self, conference: str, year: int) -> Dict:
        invitation_map = {
            "ICLR":   f"ICLR.cc/{year}/Conference/-/Blind_Submission",
            "NeurIPS":f"NeurIPS.cc/{year}/Track1/-/Submission",
            "ICML":   f"ICML.cc/{year}/Conference/-/Submission",
        }
        invitation = invitation_map.get(conference)
        if not invitation:
            raise ValueError(f"Conferenza sconosciuta: {conference}")

        venue_boost = {"ICLR": 2.0, "NeurIPS": 2.0, "ICML": 2.0}.get(conference, 1.0)
        docs, new_cnt = [], 0

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.API_BASE}/notes",
                params={"invitation": invitation, "details": "replyCount", "limit": 1000},
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"OpenReview {conference} {year}: HTTP {resp.status}")
                    return {"source": "openreview", "conference": conference, "year": year, "found": 0, "new": 0, "documents": []}
                data = await resp.json()

        for note in data.get("notes", []):
            pid     = note["id"]
            if self.db.exists("openreview", pid):
                continue
            content = note.get("content", {})
            domains, relevance = self.classifier.classify(
                content.get("title", ""), content.get("abstract", "")
            )
            doc = ScientificDocument(
                reservoir_id="",
                source="openreview",
                external_id=pid,
                title=content.get("title", ""),
                authors=content.get("authors", []),
                abstract=content.get("abstract", ""),
                year=year,
                venue=f"{conference} {year}",
                html_url=f"https://openreview.net/forum?id={pid}",
                domains=domains,
                keywords=content.get("keywords", []),
                relevance_score=relevance * venue_boost,
            )
            doc.reservoir_id = doc.generate_reservoir_id()
            docs.append(doc)
            if self.db.insert(doc):
                new_cnt += 1

        self.db.log_fetch("openreview", f"{conference}/{year}", len(data.get("notes", [])), new_cnt, 0)
        return {"source": "openreview", "conference": conference, "year": year, "found": len(data.get("notes", [])), "new": new_cnt, "documents": docs}


# ===========================================================================
# Orchestrator
# ===========================================================================

class ReservoirOrchestrator:

    def __init__(
        self,
        base_dir:      Path = BASE_DIR,
        vector_url:    str  = _DEFAULT_VECTOR_URL,
        magellano_url: str  = _DEFAULT_MAGELLANO_URL,
        standalone:    bool = False,
    ):
        self.base_dir      = base_dir
        self.vector_url    = vector_url
        self.magellano_url = magellano_url
        self.standalone    = standalone
        self.db            = ReservoirDatabase(base_dir / "reservoir.db")
        self.classifier    = KeywordClassifier(base_dir / "config" / "keywords.yml")
        self._init_dirs()

    def _init_dirs(self):
        for subdir in [
            "00_queue", "01_ingesting",
            "02_reservoir/by_source", "02_reservoir/by_domain", "02_reservoir/by_year",
            "03_embeddings", "04_failed",
        ]:
            (self.base_dir / subdir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------

    async def run_fetch_cycle(
        self,
        sources:     Optional[List[str]] = None,
        days:        int  = 7,
        max_results: int  = 500,
    ) -> Dict:
        sources = sources or ["arxiv", "semantic_scholar", "kdnuggets"]
        results: Dict[str, Dict] = {}

        if "arxiv" in sources:
            fetcher = ArxivFetcher(self.db, self.classifier)
            results["arxiv"] = await fetcher.fetch_recent(days=days, max_results=max_results)
            if self.standalone:
                for doc in results["arxiv"]["documents"]:
                    save_standalone(doc)

        if "semantic_scholar" in sources:
            s2 = SemanticScholarFetcher(
                self.db, self.classifier,
                api_key=os.getenv("S2_API_KEY"),
            )
            domains_to_query = [
                "multi-agent systems", "neural cryptography",
                "Mamba state space model", "mixture of experts LLM",
                "retrieval augmented generation",
            ]
            for i, domain in enumerate(domains_to_query):
                key = f"s2_{domain[:20]}"
                if i > 0:
                    await asyncio.sleep(2.0)  # stay under S2 unauthenticated rate limit (~1 req/s)
                results[key] = await s2.search_by_keywords([domain], limit=30)
                if self.standalone:
                    for doc in results[key]["documents"]:
                        save_standalone(doc)

        if "kdnuggets" in sources:
            kd = KDnuggetsFetcher(self.db, self.classifier)
            results["kdnuggets"] = await kd.fetch_articles(max_age_days=14)
            if self.standalone:
                for doc in results["kdnuggets"]["documents"]:
                    save_standalone(doc)

        if "openreview" in sources:
            orf = OpenReviewFetcher(self.db, self.classifier)
            for conf in ["ICLR", "NeurIPS", "ICML"]:
                for year in [2024, 2025]:
                    try:
                        r = await orf.fetch_conference(conf, year)
                        results[f"{conf}_{year}"] = r
                        if self.standalone:
                            for doc in r["documents"]:
                                save_standalone(doc)
                    except Exception as e:
                        logger.error(f"OpenReview {conf}/{year}: {e}")

        if "paperswithcode" in sources:
            pwc = PapersWithCodeFetcher(self.db, self.classifier)
            results["paperswithcode"] = await pwc.fetch_sota_papers()
            if self.standalone:
                for doc in results["paperswithcode"]["documents"]:
                    save_standalone(doc)

        # Riepilogo
        total_new = sum(v.get("new", 0) for v in results.values())
        logger.info(f"Fetch completato: {total_new} nuovi documenti")
        return results

    # ------------------------------------------------------------------

    async def run_ingestion_cycle(self, batch_size: int = 50) -> Dict:
        if self.standalone:
            logger.info("Modalità standalone: ingestion skippata (usa 'fetch' per popolare il filesystem).")
            return {"mode": "standalone", "processed": 0}

        pending = self.db.get_pending_ingestion(batch_size)
        logger.info(f"Ingestion: {len(pending)} documenti in coda")
        successes, failures = 0, 0

        async with MagellanoBridge(self.vector_url, self.magellano_url) as bridge:
            vector_ok, magellano_ok = await bridge.health_check()
            if not vector_ok:
                logger.error(f"Vector Service non raggiungibile su {self.vector_url} — abort ingestion")
                return {"processed": 0, "successes": 0, "failures": 0, "error": "vector_service_unreachable"}
            if not magellano_ok:
                logger.warning(f"Magellano API non raggiungibile su {self.magellano_url} — solo Tier 0")

            for row in pending:
                doc = ScientificDocument(
                    reservoir_id   = row["reservoir_id"],
                    source         = row["source"],
                    external_id    = row["external_id"],
                    title          = row["title"],
                    authors        = json.loads(row.get("authors") or "[]"),
                    abstract       = row.get("abstract") or "",
                    full_text      = row.get("full_text"),
                    year           = row.get("year", 0),
                    venue          = row.get("venue", ""),
                    doi            = row.get("doi"),
                    citation_count = row.get("citation_count", 0),
                    domains        = json.loads(row.get("domains") or "[]"),
                    keywords       = json.loads(row.get("keywords") or "[]"),
                    relevance_score= row.get("relevance_score", 0.0),
                )
                ok = await bridge.ingest_document(doc)
                if ok:
                    self.db.mark_ingested(doc.reservoir_id)
                    successes += 1
                    if magellano_ok:
                        await bridge.cache_magellano_embedding(doc)
                else:
                    self.db.mark_ingestion_failed(doc.reservoir_id, "ingest_document returned False")
                    failures += 1

        logger.info(f"Ingestion: {successes} ok, {failures} falliti")
        return {"processed": len(pending), "successes": successes, "failures": failures}


# ===========================================================================
# CLI
# ===========================================================================

async def _main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Scientific Reservoir Fetcher — Magellano RAG 2-Tier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
          Esempi:
            # Fetch standalone (nessun servizio richiesto)
            python fetcher.py fetch --standalone

            # Fetch + ingest integrato
            python fetcher.py fetch
            python fetcher.py ingest

            # Solo arXiv ultimi 3 giorni
            python fetcher.py fetch --sources arxiv --days 3 --max 200

            # Pipeline completa
            python fetcher.py full --sources arxiv semantic_scholar

            # Statistiche serbatoio
            python fetcher.py stats
        """),
    )
    parser.add_argument(
        "command",
        choices=["fetch", "ingest", "stats", "full"],
        help="Comando da eseguire",
    )
    parser.add_argument(
        "--sources", nargs="+",
        default=["arxiv", "semantic_scholar", "kdnuggets"],
        choices=["arxiv", "semantic_scholar", "kdnuggets", "openreview", "paperswithcode"],
        metavar="SOURCE",
        help="Fonti da interrogare",
    )
    parser.add_argument("--days",       type=int,  default=7,   help="Giorni di look-back per arXiv")
    parser.add_argument("--max",        type=int,  default=500, help="Max risultati per fonte")
    parser.add_argument("--batch-size", type=int,  default=50,  help="Batch ingestion")
    parser.add_argument("--standalone", action="store_true",
                        help="Salva su filesystem, non posta al Vector Service")
    parser.add_argument("--vector-url",    default=_DEFAULT_VECTOR_URL,
                        help=f"URL Vector Service (default: {_DEFAULT_VECTOR_URL})")
    parser.add_argument("--magellano-url", default=_DEFAULT_MAGELLANO_URL,
                        help=f"URL Magellano API (default: {_DEFAULT_MAGELLANO_URL})")

    args = parser.parse_args()

    orchestrator = ReservoirOrchestrator(
        base_dir      = BASE_DIR,
        vector_url    = args.vector_url,
        magellano_url = args.magellano_url,
        standalone    = args.standalone,
    )

    if args.command == "fetch":
        results = await orchestrator.run_fetch_cycle(
            sources=args.sources, days=args.days, max_results=args.max
        )
        print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "documents"} for k, v in results.items()}, indent=2, default=str))

    elif args.command == "ingest":
        result = await orchestrator.run_ingestion_cycle(args.batch_size)
        print(json.dumps(result, indent=2))

    elif args.command == "stats":
        stats = orchestrator.db.stats()
        print(json.dumps(stats, indent=2))

    elif args.command == "full":
        await orchestrator.run_fetch_cycle(sources=args.sources, days=args.days, max_results=args.max)
        result = await orchestrator.run_ingestion_cycle(args.batch_size)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
