# Agentic Search - Agente Conversazionale con Intelligenza Ibrida

> Reference corpus: catalog search (books). The agent loop is domain-agnostic.

# Panoramica del Progetto e Design

Questo progetto implementa un agente di ricerca conversazionale (Agentic Search), un agente AI conversazionale production-ready per la ricerca di libri in linguaggio naturale. Il sistema combina tecniche di fuzzy matching con comprensione semantica avanzata per gestire efficacemente errori di trascrizione vocale, query multilingue e conversazioni multi-turno.

- **Architettura di Ricerca Ibrida**: Combina fuzzy matching (RapidFuzz) con embeddings semantici (SentenceTransformers) per accuratezza ottimale

# Caratteristiche Principali

**Correzione Automatica di Errori**: Gestisce typo e errori di trascrizione vocale

**Comprensione Semantica**: Trova libri per temi emotivi e concetti astratti

**Supporto Multilingue**: Processa query in italiano abbinate a libri in diverse lingue

**Conversazioni Multi-turno**: Mantiene il contesto attraverso query sequenziali

**Alte Prestazioni**: Tempo di risposta medio di ~40ms (75x migliore del target di 3s)

# Performance (Stress Test Reale)

**Risultati test A/B su 50+ query**:

| Risultato | Valore | Impatto |
|-----------|--------|---------|
| **Risultato Notevole** | Fuzzy: 0% → Semantic: 54.2% | Semantic trova risultati dove fuzzy fallisce |
| **Boost Confidenza** | 21.9% → 77.3% | **3.5x di miglioramento** su query emotive |
| **Moltiplicazione Risultati** | 1 libro → 10 libri | **10x più risultati** su concetti astratti |
| **Precisione (Autori)** | 90% match esatto | Fuzzy eccelle nella ricerca autore/titolo |
| **Latenza** | Fuzzy: 2-5ms, Semantic: 30-50ms | Entrambi **75x più veloci** del target di 3s |

**Insight Chiave**: Semantic raggiunge **70% delle query sopra 40% di confidenza** vs 37% di fuzzy

Per i risultati completi dello stress test, consultare PERFORMANCE_ANALYSIS.md.

## Quick Start

### Prerequisiti

- Python 3.8+
- Windows/Linux/macOS

### Installazione

```bash
# Clone repository
git clone https://github.com/Gyros4me/ai-os-architecture.git
cd ai-os-architecture/use-cases/UC05_Agentic_Search

# Crea ambiente virtuale
python -m venv .venv

# Su Windows: 
.venv\Scripts\activate

# Installa dipendenze
pip install -r requirements.txt
```

### Esegui CLI Interattiva

```bash
# Modalità fuzzy-only (veloce, deterministica)
python run_cli.py --fuzzy

# Modalità semantic (comprensione concettuale)
python run_cli.py --semantic
```

### Esegui Server API

```bash
uvicorn src.api:app --reload
# Visita http://localhost:8000/docs per la documentazione API interattiva
```
# Documentazione API disponibile su http://localhost:8000/docs

## Architettura

### Componenti Core

```
src/
├── agent.py                    # Agente conversazionale principale
├── search_engine.py            # Motore fuzzy matching
├── semantic_search_engine.py   # Motore ibrido semantic + fuzzy
├── context_manager.py          # Tracciamento conversazioni multi-turno
├── fuzzy_matcher.py            # RapidFuzz + matching fonetico
├── data_loader.py              # Dataset (45 libri con descrizioni ricche)
└── models.py                   # Modelli dati Pydantic

```

### Strategia di Ricerca (Modalità Semantic)

1. **Intent Detection**: Classifica la query come autore/titolo/keyword/follow-up
2. **Fuzzy Matching**: Corregge typo nelle ricerche per autore/titolo
3. **Ricerca Semantica**: Per query keyword, codifica la query e confronta con embeddings dei libri
4. **Context Tracking**: Mantiene lo storico conversazione per query multi-turno

### Caratteristiche Prestazionali

| Modalità | Latenza Media | Caso d'Uso |
|----------|---------------|------------|
| Fuzzy | ~5ms | Ricerca autore/titolo con typo |
| Semantic | ~30ms | Temi concettuali/emotivi |

## Testing

### Unit Test

```bash
pytest tests/ -v
# 13 test, 93% code coverage
```

### Test Funzionali

```bash
# Esegui demo scenari
python demo.py

# Comparazione A/B (fuzzy vs semantic)
python demo_semantic_ab_test.py

# Performance benchmarking
python benchmark.py
```

## Decisioni di Design

### Perché Ibrido (Fuzzy + Semantic)?

- **Fuzzy eccelle in**: Matching esatto con typo, velocità, determinismo
- **Semantic eccelle in**: Comprensione concettuale, temi emotivi, query complesse
- **Ibrido vince**: Combina entrambi i punti di forza automaticamente in base al tipo di query

### Perché Sentence-Transformers?

- **Modello**: `all-MiniLM-L6-v2` (leggero, embeddings 384-dim)
- **Trade-off**: Accuratezza bilanciata vs velocità per dataset 45 libri
- **Scalabilità**: Può essere sostituito con vector DB (FAISS/Pinecone) per dataset più grandi

### Design Dataset

45 libri selezionati per dimostrare:
- **Serie/saghe**: LOTR, Harry Potter, Millennium (per test multi-turno)
- **Varietà emotiva**: Romantico, malinconico, horror, filosofico
- **Descrizioni ricche**: 25-30 parole per libro con vocabolario emotivo per matching semantico

## Funzionalità e Stato

| Funzionalità | Implementazione | Stato |
|-----------|-----------------|-------|
| Fuzzy matching per typo | RapidFuzz + fonetico | ✅ |
| Matching titoli multilingue | Unidecode + langdetect | ✅ |
| Tracciamento contesto conversazione | Context manager basato su sessione | ✅ |
| Tempo risposta <3s | ~40ms medio (75x meglio) | ✅ |
| Servizio API | FastAPI con endpoint /search | ✅ |
| Unit test | 13 test, 93% coverage | ✅ |

## Deployment

### Docker

```bash
# Build ed esegui
docker-compose up

# API disponibile su http://localhost:8000
```

### Configurazione Docker

Vedi `docker-compose.yml` per:
- Variabili ambiente (BOOKS_CSV_PATH, CONTEXT_TTL_MINUTES)
- Mount volumi per dataset personalizzati
- Health check
- Servizi opzionali Redis/Prometheus/Grafana

## Strategia di Valutazione

### Metriche

1. **Accuratezza Retrieval**: Precision@K e Recall@K su test set annotato
2. **Latenza**: Tempi di risposta P50, P95, P99
3. **Coerenza Contesto**: Score continuità sessione per dialoghi multi-turno

### Ottimizzazione Token (per integrazione LLM)

- **Context caching**: Storage sessione backed da Redis
- **Re-ranking only**: Usa LLM per raffinare top-K, non per ricerca iniziale
- **Pre-computazione embeddings**: Genera una volta all'avvio

## Miglioramenti Futuri

1. **Vector Database**: FAISS/Pinecone per 10K+ libri
2. **Neural Re-ranking**: Cross-encoder per raffinamento risultati top-K
3. **Query Expansion**: Sinonimi e termini correlati
4. **Gestione Negazione**: Supporto "fantasy ma non Tolkien"
5. **Personalizzazione**: Apprendimento preferenze utente

## Struttura Del Progetto
text
```
UC05_Agentic_Search/
├── src/                        # Moduli core
├── tests/                      # Unit test
├── demo.py                     # Demo interattiva
├── demo_semantic_ab_test.py    # Comparazione Fuzzy vs Semantic
├── benchmark.py                # Performance benchmarking
├── requirements.txt            # Dipendenze Python
├── docker-compose.yml          # Setup Docker
├── README.md                   # Questo file
├── PERFORMANCE_ANALYSIS.md     # Risultati stress test reale (50+ query)
└── TEST_SCENARIOS.md           # Risultati test A/B
```
## Licenza

Questo progetto è distribuito sotto licenza MIT. Per i dettagli completi, consultare il file LICENSE.txt.
 
 
