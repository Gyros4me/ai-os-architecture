TEST LIST COMPLETA - Vector Ingestion Service
Preparazione Ambiente
Table
Step	Azione	Comando/URL
1	Avvia servizi	docker-compose up -d
2	Verifica health	curl http://localhost:8003/health
3	Apri Swagger UI	http://localhost:8003/docs
4	Verifica n8n	http://localhost:5678
FASE 1: Ingestione Documenti (10 Documenti Misti)
1.1 Documenti di Test da Preparare
![alt text](image-8.png)
![alt text](image-9.png)
Table
#	Tipo	Nome File	Contenuto	Source ID
1	TXT	manuale_kia_sportage.txt	Estratto manuale utente KIA Sportage (2-3 pagine)	manual_kia_sportage_2024
2	TXT	faq_adas.txt	FAQ sistema ADAS (domande/risposte)	faq_adas_system
3	PDF	listino_prezzi_kia.pdf	Listino prezzi modelli KIA 2024	pricing_kia_2024
4	PDF	guida_garanzia.pdf	Guida garanzia e manutenzione	warranty_guide_kia
5	JSON	configurazioni_ev6.json	Configurazioni tecniche KIA EV6	specs_ev6_config
6	JSON	dealer_network.json	Rete concessionari Italia	dealer_network_it
7	CSV	ricambi_disponibili.csv	Catalogo ricambi con codici e prezzi	parts_catalog_2024
8	CSV	storico_manutenzioni.csv	Storico interventi manutenzione	service_history_template
9	TXT	procedura_sos.txt	Procedura emergenza/SOS KIA	emergency_procedure_sos
10	PDF	infografica_ricarica_ev.pdf	Guida ricarica veicoli elettrici	ev_charging_guide
FASE 2: Test Script PowerShell
2.1 Test Base con riprova_fixed.ps1
powershell
Copy
# Esegui test verboso base
.\riprova_fixed.ps1

# Verifica output atteso:
# - Upload documento testuale
# - Ricerca semantica dettagliata con similarità
# - Lista documenti nel sistema
# - Test multiple query
Checklist:
[ ] Upload /upload/text funziona con Content-Type: application/x-www-form-urlencoded
[ ] Search /search restituisce risultati ordinati per similarità
[ ] Documents /documents elenca i documenti caricati
[ ] Statistiche similarità (min/max/avg) calcolate correttamente
2.2 Test Qualità RAG con RAG_Quality_Chunking_Analysis.ps1
powershell
Copy
# Test completo con ground truth
.\RAG_Quality_Chunking_Analysis.ps1 -BaseUrl "http://localhost:8003" -VerboseOutput -GenerateReport

# Verifica report JSON generato
Get-Content "RAG_Quality_Report_*.json" | ConvertFrom-Json
Checklist:
[ ] 10 documenti caricati con successo
[ ] Wait-ServiceIndexed polling attivo funziona (non più sleep fisso)
[ ] 51 ground truth queries eseguite
[ ] Deduplicazione source_id nel ranking funziona
[ ] Preservazione sintattica verificata (tabelle, code block, email)
[ ] Report finale con score A/B/C/D generato
[ ] Metriche: Success rate > 80%, Avg rank < 2.5
Metriche attese dal report:
JSON
Copy
{
  "summary": {
    "success_rate": ">85%",
    "avg_rank": "<2.0",
    "avg_similarity": ">0.75",
    "high_relevance_accuracy": ">90%",
    "syntactic_preservation_rate": ">85%"
  }
}
2.3 Test Semantici Avanzati con semantic_search_complete_tests.ps1
powershell
Copy
# Menu interattivo - esegui tutti i test
.\semantic_search_complete_tests.ps1

# Selezione: 11 (Run ALL Tests)
Checklist per ogni categoria:
Table
Test	Verifica
Basic Semantic Search	Parametri k e min_similarity rispettati, risultati ordinati
Multilingual (IT/EN)	Query italiano/inglese restituiscono risultati consistenti
Domain-Specific	Query tecniche KIA (ADAS, DPF, EV6) trovano documenti rilevanti
Query Variations	Typo tolleranza, lunghezza query variabile gestita
Threshold Comparison	Threshold 0.5/0.6/0.7/0.8/0.9 filtrano correttamente
Negative Queries	Query irrilevanti (pizza, Parigi) restituiscono 0-1 risultati
Documents Listing	Paginazione e metadati corretti
Collections	Collezione document_chunks esiste
Concurrent Queries	10 query parallele, latenza P95 < 200ms
Dead Letter Queue	Query malformate gestite, endpoint DLQ accessibile
2.4 Test Integrazione n8n con n8n_vs_vectorservice_demo.ps1
powershell
Copy
# Verifica orchestrazione n8n -> Vector Service
.\n8n_vs_vectorservice_demo.ps1

# Prerequisito: workflow n8n attivo su http://localhost:5678/webhook/demo-health
Checklist:
![alt text](image-7.png)
[ ] Webhook n8n risponde (porta 5678)
[ ] n8n chiama Vector Service via Docker internal DNS (vector-service:8000)
[ ] Response include raw_response con status vettoriale
[ ] Architettura: Client → n8n → Vector Service → Response verificata
[ ] Confronto direct vs n8n-mediated restituisce stesso status
FASE 3: Test Manuali via Swagger UI
3.1 Endpoint Health & Monitoring
![alt text](image-5.png)
Table
Endpoint	Metodo	Test	Expected
/health	GET	Esegui su Swagger	{"status": "healthy", "services": {...}}
/stats	GET	Verifica metriche	Statistiche embedder, vector_store, DLQ
/config	GET	Controlla config	MAX_FILE_SIZE_MB, DEFAULT_CHUNK_SIZE
/api-spec	GET	Lista endpoint	Array di tutti gli endpoint disponibili
3.2 Endpoint Ingestion (test con i 10 documenti preparati)
POST /upload/text (Documenti 1, 2, 9)
JSON
Copy
// Body (form-data):
content: "Testo completo del manuale KIA Sportage..."
source_id: "manual_kia_sportage_2024"
metadata: {"category": "manuali", "model": "sportage", "year": 2024}
Verifica:
[ ] Response chunks_count > 0
[ ] processing_time_ms < 5000
[ ] document_id generato
POST /upload/pdf (Documenti 3, 4, 10)
Usa "Try it out" → Choose File → Seleziona PDF
Verifica:
[ ] Upload file multipart funziona
[ ] pages estratte correttamente
[ ] file_size_bytes corrisponde
POST /upload/csv (Documenti 7, 8)
JSON
Copy
// Body (form-data):
file: [seleziona CSV]
group_by: "category"
max_rows_per_chunk: 50
Verifica:
[ ] Parsing CSV con pandas
[ ] Raggruppamento per colonna (se specificato)
[ ] rows_per_chunk rispettato
POST /upload/text per JSON (Documenti 5, 6)
Tratta JSON come testo strutturato:
JSON
Copy
content: "{\"model\": \"EV6\", \"battery\": \"77.4 kWh\", ...}"
source_id: "specs_ev6_config"
3.3 Endpoint Search & Query
POST /search - Test Matrice
![alt text](image-4.png)
Table
Query	n_results	min_similarity	source_filter	Expected
"reset password"	5	0.7	-	Risultati rilevanti
" Sportage ADAS"	3	0.8	manual_kia_sportage_2024	Solo da manuale
"ricambi freni"	10	0.5	-	Catalogo ricambi
"emergenza SOS"	5	0.6	-	Procedura SOS
Verifica Response:
JSON
Copy
{
  "query": "reset password",
  "results_count": 5,
  "results": [
    {
      "content": "...",
      "similarity": 0.89,
      "metadata": {"source": "manual_kia_sportage_2024"}
    }
  ]
}
GET /documents
![alt text](image-3.png)
Table
Parametro	Valore	Verifica
limit	10	Paginazione funziona
offset	0	Offset iniziale
document_type	manual	Filtro per tipo
GET /collections
Verifica collezione document_chunks esista con total_chunks > 0
3.4 Endpoint DLQ (Dead Letter Queue)
![alt text](image-2.png)
Table
Endpoint	Test	Expected
GET /dlq/stats	Verifica statistiche	failed_chunks, failed_files, reasons
GET /dlq/failed-chunks	Lista con paginazione	Array chunk falliti
GET /dlq/failed-files	Lista file falliti	Array file falliti
POST /dlq/retry/{chunk_id}	Retry chunk specifico	{"status": "retrying"}
POST /dlq/test-failure	Simula fallimento	Test chunk creato
DELETE /dlq/clear-permanent	Pulisci vecchi fallimenti	{"deleted_chunks": N}
Test DLQ - Simulazione Errore:
Chiama POST /dlq/test-failure
Verifica chunk appare in GET /dlq/failed-chunks
Esegui POST /dlq/retry/{chunk_id}
Verifica stato aggiornato
3.5 Endpoint Embeddings
![alt text](image-1.png)
Table
Endpoint	Test	Verifica
GET /embeddings/info	Info modello	model_name, embedding_dimension: 384
POST /embeddings/batch	Batch di testi	Array embeddings restituito
POST /embeddings/benchmark	Performance	throughput_docs_per_sec, avg_latency_ms
Benchmark Test:
JSON
Copy
// POST /embeddings/benchmark
{
  "sample_size": 100,
  "iterations": 3,
  "batch_size": 32
}
FASE 4: Test Docker & Infrastructure
4.1 Container Health
bash
Copy
# Verifica stato container
docker-compose ps

# Log servizio
docker-compose logs -f vector-service

# Verifica healthcheck
docker inspect --format='{{.State.Health.Status}}' vector-service
4.2 Persistenza Dati
Table
![alt text](image.png)
Test	Comando	    Verifica
ChromaDB persistente	ls -la ./data/chroma_db/	Directory esiste, file creati
DLQ SQLite	ls -la ./data/dlq.db	Database esiste
n8n data	ls -la ./n8n_data/	Workflow e configurazioni persistite
4.3 Restart Test
bash
Copy
# Test resilienza
docker-compose restart vector-service
# Attendi 10 secondi
curl http://localhost:8003/health
# Verifica documenti ancora presenti
curl "http://localhost:8003/documents?limit=10"
FASE 5: Test End-to-End Scenario Completo
Scenario: "Cliente KIA cerca informazioni"
powershell
Copy
# Step 1: Carica tutti i documenti
.\RAG_Quality_Chunking_Analysis.ps1

# Step 2: Simula query cliente via n8n
Invoke-RestMethod -Uri "http://localhost:5678/webhook/demo-health" -Method Get

# Step 3: Ricerca semantica multi-formato
$queries = @(
    "Come funziona il lane assist sulla Sportage?",
    "Quanto costa la batteria della EV6?",
    "Dove è il concessionario più vicino a Milano?",
    "Codice ricambio pastiglie freno Ceed",
    "Procedura se la macchina non si avvia"
)

foreach ($q in $queries) {
    $body = "query=$([System.Uri]::EscapeDataString($q))&n_results=3&min_similarity=0.7"
    $r = Invoke-RestMethod -Uri "http://localhost:8003/search" -Method Post -Body $body
    Write-Host "Query: $q -> $($r.results.Count) risultati"
}
Checklist Finale Consolidata
✅ Funzionalità Core
[ ] Upload TXT, PDF, CSV, JSON funzionanti
[ ] Search semantica con filtri e threshold
[ ] Chunking preserva struttura sintattica
[ ] Embeddings 384-dim generati correttamente
✅ Qualità & Performance
[ ] RAG Quality Report generato (score > 75%)
[ ] Latenza search < 100ms (p95)
[ ] Concurrent queries gestite
[ ] Multilingual search funzionante
✅ Resilienza
[ ] DLQ traccia fallimenti
[ ] Retry mechanism funziona
[ ] Healthcheck Docker passa
[ ] Persistenza dati confermata
✅ Integrazione
[ ] n8n orchestration funziona
[ ] Swagger UI accessibile
[ ] CORS configurato (env-based)
[ ] Basic auth n8n configurabile
Comandi Rapidi Riepilogativi
bash
Copy
# Avvio completo
docker-compose up -d && sleep 10

# Test rapido salute
curl http://localhost:8003/health && curl http://localhost:5678/webhook/demo-health

# Esecuzione test suite PowerShell
.\riprova_fixed.ps1
.\RAG_Quality_Chunking_Analysis.ps1 -GenerateReport
.\semantic_search_complete_tests.ps1  # Seleziona 11

# Verifica finale
docker-compose ps
ls ./data/chroma_db/
ls ./test_results/
Questa test list copre tutti gli endpoint (20+), tutti gli script PowerShell (4 script), e tutti i formati documento (TXT, PDF, CSV, JSON) in modo omogeneo e ripetibile