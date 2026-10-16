# Vector Ingestion Service

> Servizio self-hosted per elaborazione semantica di documenti con ricerca vettoriale e integrazione n8n

Servizio FastAPI production-ready per ingerire documenti (testo, PDF, CSV), generare embeddings ed eseguire ricerche semantiche. Include Dead Letter Queue (DLQ) per gestione fallimenti, suite di test completa e integrazione con workflow n8n.

---

## Funzionalità

- **Formati multipli**: Ingestione documenti text, PDF e CSV
- **Ricerca semantica**: Similarità vettoriale con sentence-transformers
- **Dead Letter Queue**: Logica di retry automatico e tracciamento fallimenti
- **Production ready**: Gestione errori, logging e monitoring completi
- **Integrazione n8n**: Automazione workflow via REST API
- **Copertura test**: 65 test che coprono tutti gli endpoint e casi limite
- **Supporto Docker**: Pronto per deployment containerizzato

---

## Quick Start

### Prerequisiti

- Python 3.11+ (the Docker image uses 3.11)
- 16GB RAM consigliati
- Virtual environment (consigliato)

### Installazione

```bash
# Clone repository
git clone https://github.com/Gyros4me/ai-os-architecture
cd ai-os-architecture/use-cases/UC06_Vector_Ingestion

# Virtual python environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Dipendenze
pip install -r requirements.txt
```

### Avvio Servizio

```bash
# Start servizio
uvicorn src.api.main:app --host 0.0.0.0 --port 8003 --reload

# Disponibile su:
# - API: http://localhost:8003
# - Docs: http://localhost:8003/docs
# - Dashboard: http://localhost:8003
```

### Test

```bash
# Validazione rapida
pytest -v

# Output verbose con metriche
pytest -v -s --tb=short

# Report HTML
pytest -v -s --html=test_report.html --self-contained-html
```

---

## Struttura Progetto

```
vector_ingestion_service/
├── src/
│   ├── api/
│   │   ├── main.py          # Applicazione FastAPI con tutti gli endpoint
│   │   └── schemas.py       # Modelli Pydantic per validazione
│   └── services/
│       ├── embedder.py      # Servizio embedding sentence-transformer
│       ├── processor.py     # Chunking e processing documenti
│       ├── vector_store.py  # Interfaccia storage vettoriale ChromaDB
│       └── dlq.py           # Implementazione Dead Letter Queue
├── tests/
│   ├── test_dlq_api.py                          # Test endpoint DLQ
│   ├── test_embedder.py                         # Test servizio embedding
│   ├── test_integration_complete_updated.py     # Test integrazione completi
│   ├── test_n8n_integration.py                  # Test workflow n8n
│   ├── test_security.py                         # Test validazione sicurezza
│   ├── test_upload_formats.py                   # Test gestione formati
│   └── test_utility_api.py                      # Test endpoint utility
├── static/               # Asset dashboard frontend
├── n8n_workflows/        # Definizioni workflow n8n esempio
├── scientific_reservoir/ # Fetcher schedulato (profilo compose "reservoir")
├── docs/                 # Test list
├── .env.example          # Template configurazione (copiare in .env)
├── conftest.py           # Configurazione e fixture pytest
├── pytest.ini            # Impostazioni pytest
├── requirements.txt      # Dipendenze Python
├── Dockerfile            # Definizione immagine container
├── docker-compose.yml    # Orchestrazione multi-container
└── README.md             # Questo file
```

---

## Endpoint API

### Ingestion Documenti

```http
POST /upload/text
POST /upload/pdf  
POST /upload/pdf-url
POST /upload/csv
```

Upload e processing documenti con chunking automatico e generazione embeddings.
`/upload/pdf-url` scarica un PDF pubblico e usa la stessa pipeline visuale di
`/upload/pdf`. Per retrocompatibilita' con N8N, `/upload/text` accetta anche
`pdf_url` e `prefer_pdf=true`: quando presenti, il servizio indicizza il PDF
completo e usa il testo come fallback.

### Ricerca e Query

```http
POST /search              # Ricerca semantica
GET  /documents           # Lista documenti caricati
GET  /collections         # Lista collezioni disponibili
```

### RAG e Magellano

```http
POST /rag/retrieve        # Retrieval-only MiniLM, utile anche da n8n
POST /rag/query           # MiniLM retrieval + generazione Magellano, fallback MiniLM
POST /rag/stream          # Variante SSE per la dashboard
GET  /rag/health          # Stato Tier-0 vector store + Tier-2 Magellano
POST /rag/multimodal      # Media/table analysis via Magellano /v1/analyze
POST /embeddings/magellano # Embedding via Magellano /v1/embed
```

Il retrieval testuale resta su `sentence-transformers/all-MiniLM-L6-v2`.
Immagini, audio, video e tabelle non vengono embeddati da MiniLM: il servizio
li inoltra a Magellano tramite `/v1/analyze`, aggiungendo solo eventuale
contesto testuale recuperato dal vector store.

Per materiale tecnico/tabellare, i nuovi upload CSV e PDF salvano anche un
canale strutturato nel chunk: `table_markdown`, `table_json`, `formula_text`,
`formulas_json`, `source`, `page`, `section`, righe e colonne. MiniLM continua a
indicizzare il testo leggibile, mentre Magellano riceve la struttura completa in
`retrieved_chunks` per domande su singoli parametri, codici, aliquote o formule.
Per i PDF gia' presenti nel vector store serve re-ingestion per ottenere le
tabelle native estratte con `pdfplumber`; il client applica comunque un fallback
euristico sui chunk esistenti.

Il bridge RAG accetta anche campi visuali/strutturali prodotti da Magellano o
dall'ingestion: `image_url`, `page_image_url`, `visual_url`, `asset_path`,
`table_html`, `formula_latex`. La dashboard renderizza inline gli asset indicati
come `Asset visuale: ...`; gli `asset_path` locali sono serviti da
`GET /visual/asset?path=...` solo se ricadono nelle root autorizzate
(`static`, `data`, `assets`, `uploads`, oppure `VISUAL_ASSET_ROOTS`).
Il testo estratto dai PDF viene normalizzato in ingestion e prima del prompt RAG
per ridurre ligature/font artifact (`fi`, `ff`, `ti`, `tti`) e mojibake comune.
Il prompt Magellano tratta i chunk come fonti, non istruzioni, e richiede asset
visuali solo da URL/path reali o da `source+page`.

### PDF Visual Enrichment

L'endpoint `POST /upload/pdf` puo' arricchire i chunk prima dell'indicizzazione:

- `extract_page_images=true`: renderizza ogni pagina PDF in PNG con PyMuPDF.
- `extract_tables=true`: estrae tabelle native con pdfplumber e fallback testuale.
- `extract_formulas=true`: salva righe tecniche/formule come `formula_text`,
  `formula_latex`, `formulas_json`.

Variabili utili:

```bash
VISUAL_EXPORT_ROOT=/app/data/visual
VISUAL_ASSET_URL_BASE=/visual/asset?path=
VISUAL_ASSET_ROOTS=/app/data/visual,/app/static,/app/data,/app/assets,/app/uploads
MAGELLANO_VISUAL_ASSET_ROOT=/path/shared/with/magellano/pdf_pages
PDF_EXTRACT_PAGE_IMAGES=true
PDF_PAGE_IMAGE_DPI=140
PDF_PAGE_IMAGE_MAX_PAGES=250
```

Se `MAGELLANO_VISUAL_ASSET_ROOT` punta a una directory realmente condivisa con il
Mac mini, i chunk inviano `asset_path` nel formato visto da Magellano. Il root
puo' essere sia la directory visuale padre sia direttamente `.../pdf_pages`: il
client evita il doppio prefisso `pdf_pages/pdf_pages`. In ogni caso il
client conserva anche `page_image_url` servibile via `/visual/asset`.

Per arXiv/Semantic Scholar il workflow N8N aggiornato passa `pdf_url` al Vector
Service: i paper con PDF pubblico generano quindi immagini pagina, tabelle e
formule; KDnuggets resta testo/RSS salvo allegati espliciti.

Se Vector Service gira in Docker e Magellano gira sulla macchina host a
`http://localhost:8004`, imposta `MAGELLANO_URL=http://host.docker.internal:8004`
nel file `.env`. Se Magellano gira su un altro host, usa il suo URL raggiungibile
dalla rete del container.

### Dead Letter Queue

```http
GET    /dlq/stats              # Statistiche DLQ
GET    /dlq/failed-chunks      # Lista chunk falliti
GET    /dlq/failed-files       # Lista file falliti
POST   /dlq/retry/{chunk_id}   # Retry chunk fallito
DELETE /dlq/clear-permanent    # Cancella fallimenti permanenti
```

### Monitoring & Health

```http
GET /health    # Health check servizio
GET /stats     # Statistiche sistema
GET /config    # Configurazione servizio
```

### Documentazione

```http
GET /docs         # Swagger UI
GET /redoc        # Documentazione ReDoc
GET /openapi.json # Specifica OpenAPI
```

---

## Integrazione n8n

Il servizio fornisce endpoint REST API che si integrano con workflow n8n.

### Workflow Disponibili

In `n8n_workflows/`:

- **Vector Service Gateway**: Dimostra interlavoro con servizio vector-service (operazioni upload e ricerca documenti
- **Mock Workflow**: Esempio struttura workflow per testing
- Workflow aggiuntivi per vari scenari di automazione

### Demo Integrazione

```bash
# Esegui vector-service + n8n con Docker
docker compose up -d --build
# n8n: http://localhost:5678  (importa i workflow da n8n_workflows/)
```

### Esempio Uso in n8n

```json
{
  "url": "http://localhost:8003/upload/text",
  "method": "POST",
  "body": {
    "content": "Contenuto documento qui",
    "source_id": "n8n_document_001"
  }
}
```

---

## Configurazione

Configurazione servizio via variabili ambiente o default in `main.py`:

```python
MAX_FILE_SIZE_MB = 50
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 100
DEFAULT_BATCH_SIZE = 50
CHROMA_PERSIST_DIR = "./data/chroma_db"
```

### Modello Embedding

Default: `sentence-transformers/all-MiniLM-L6-v2`
- Dimensione embedding: 384
- Inferenza veloce su CPU
- Bilanciamento accuracy/velocità

---

## Testing

### Panoramica Test Suite

- **65 test** che coprono tutte le funzionalità
- **Zero warning** con validazione completa
- **Metriche performance** tracciate in ogni test
- **Test integrazione** validano flussi end-to-end

### Categorie Test

```bash
# Test unitari
pytest tests/test_embedder.py -v -s

# Test integrazione
pytest tests/test_integration_complete_updated.py -v -s

# Integrazione n8n
pytest tests/test_n8n_integration.py -v -s

# Test sicurezza
pytest tests/test_security.py -v -s
```

### Script Validazione

```bash
python validate_test_improvements.py
```

Valida:
- Configurazione pytest.ini
- Setup logging conftest.py
- Assenza return statements problematici nei test

---

## Performance

### Metriche Misurate

- **Ingestione testo**: ~4.3 docs/sec (CPU-only, T430s)
- **Latenza ricerca**: <50ms per query tipiche
- **Generazione embedding**: ~145ms per batch (32 testi)
- **Tempo risposta API**: <200ms media

Tutte le metriche misurate su hardware: Lenovo T430s, 16GB RAM, inferenza CPU-only.

---

## Deployment Docker

### Singolo Container

```bash
docker build -t vector-service .
docker run -p 8003:8003 -v $(pwd)/data:/app/data vector-service
```

### Con n8n (Docker Compose)

```bash
docker-compose up -d

# Servizi:
# - Vector Service: http://localhost:8003
# - n8n: http://localhost:5678
```

---

## Gestione Errori

### Dead Letter Queue (DLQ)

Operazioni fallite tracciate automaticamente in DLQ con:
- Motivo fallimento e timestamp
- Conteggio retry
- Dati documento/chunk originale

Logica retry:
- Retry automatico per fallimenti transienti
- Retry manuale via `/dlq/retry/{chunk_id}`
- Tracciamento fallimenti permanenti dopo max retry

### Logging

Log strutturati disponibili in directory `logs/`:
- Log applicazione: `app.log`
- Log errori: Stack trace dettagliati
- Logging request/response per debug

---

## Sviluppo

### Aggiungere Nuovi Endpoint

1. Definire endpoint in `src/api/main.py`
2. Aggiungere schema Pydantic in `src/api/schemas.py`
3. Implementare logica business in `src/services/`
4. Aggiungere test in `tests/`

### Esecuzione in Development Mode

```bash
uvicorn src.api.main:app --reload --log-level debug
```

---

## Note Architetturali

### Scelte Design

- **FastAPI**: Framework API moderno, veloce, auto-documentato
- **ChromaDB**: Database vettoriale leggero ed embedded
- **Sentence-Transformers**: Modelli embedding CPU-friendly
- **Pydantic**: Validazione e serializzazione dati robusta

### Considerazioni Scalabilità

Implementazione attuale ottimizzata per:
- Deployment single machine
- Inferenza CPU-only
- Volumi documenti moderati (<10K documenti)

Per scala produzione:
- Considerare accelerazione GPU per embeddings
- Usare database vettoriale esterno (Qdrant, Weaviate, Pinecone)
- Implementare queuing request con Redis/Celery
- Aggiungere load balancing per istanze multiple

---

## Troubleshooting

### Problemi Comuni

**Servizio non si avvia**
```bash
# Verifica disponibilità porta
netstat -ano | findstr :8003

# Verifica versione Python
python --version  # Deve essere 3.12+
```

**Test falliscono**
```bash
# Verifica servizio in esecuzione
curl http://localhost:8003/health

# Verifica ambiente test
python validate_test_improvements.py
```

**Embedding lenti**
```bash
# CPU-only è atteso essere più lento
# Considerare batch size più piccoli in produzione
# Monitorare con: GET /stats
```

---
---


**Tecnologie chiave**:
- FastAPI
- ChromaDB
- sentence-transformers
- pytest
- n8n (automazione workflow)

---

## Licenza

MIT License - vedi [LICENSE](LICENSE) file per dettagli.
