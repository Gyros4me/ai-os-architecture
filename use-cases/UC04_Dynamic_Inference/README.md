# Dynamic Inference Service

## Panoramica del Progetto e Design

Questo progetto implementa un Dynamic Inference Service (Servizio di Inferenza Dinamica) in Python, utilizzando FastAPI per l'esposizione come API web. L'obiettivo principale è fornire un servizio di classificazione altamente configurabile e multi-tenant, in grado di caricare e applicare dinamicamente logiche specifiche per ciascun cliente, identificate tramite un `client_id`.

Il design è incentrato sulla separazione delle preoccupazioni e sulla configurabilità a runtime, aderendo al principio di isolamento per cliente. Il sistema è progettato per essere estensibile, mantenibile e pronto per la produzione, con la capacità di gestire diverse tipologie di modelli di machine learning e pipeline di elaborazione personalizzate per ogni cliente.

## Architettura del Sistema

Il servizio è strutturato in componenti modulari che collaborano per fornire un'esperienza di inferenza flessibile e personalizzabile:

**InferenceService (Core Logic)**: La classe centrale che orchestra l'intero processo di inferenza. Gestisce il ciclo di vita completo: caricamento della configurazione specifica del cliente, coordinazione dei passaggi sequenziali (pre-processing, predizione, post-processing, applicazione regole) e garanzia dell'isolamento tra i diversi clienti.

**Configurazione (config/clients.json)**: Un file JSON che funge da registro centrale per tutti i clienti configurati. Ogni voce nel file definisce completamente il comportamento di un cliente specifico: il modello da utilizzare, la sequenza esatta di pre-processing e post-processing da applicare, e le regole business personalizzate. Questo approccio elimina completamente la logica hardcoded e permette l'aggiornamento dinamico del comportamento del sistema a runtime (dopo il riavvio del servizio).

**Processori Dinamici (src/processors.py)**: Moduli Python caricati dinamicamente a runtime che implementano funzioni specifiche di pre-processing (es. lowercase, strip_punctuation, tokenize) e post-processing (es. add_confidence_score, format_output, filter_categories). Ogni processore è una funzione pura che trasforma l'input o l'output secondo necessità.

**Motore di Regole (src/rules.py)**: Un componente sofisticato che applica logiche condizionali complesse basate sulla configurazione specifica del cliente. Le regole possono sovrascrivere la predizione del modello basandosi su condizioni arbitrarie (presenza di parole chiave, lunghezza del testo, combinazione di fattori) per implementare la logica di business specifica di ogni cliente.

**API Rest (src/api.py)**: Un'interfaccia FastAPI completa che espone endpoint HTTP per l'interazione con il servizio InferenceService. Include documentazione automatica (OpenAPI/Swagger), validazione degli input, gestione degli errori e supporto per formati di risposta standardizzati.

**Sistema di Testing (tests/)**: Una suite completa di test unitari e di integrazione che garantisce la correttezza del sistema e la sua resilienza a diversi scenari di input, configurazioni e condizioni di errore.

## Funzionalità Implementate

| Funzionalità | Implementazione |
|-----------|-----------------|
| Supporto Multi-Cliente | La configurazione in clients.json definisce logicamente l'isolamento e la personalizzazione per client_a e client_b |
| Caricamento Dinamico | I processori sono caricati dinamicamente a runtime tramite importlib e Reflection in base ai nomi specificati nella configurazione, senza modifiche al codice sorgente |
| Configurazione Esterna | Tutto il comportamento specifico del cliente (modello, processori, regole) è definito in clients.json |
| Gestione Tipi di Modello | Il campo model.type nella configurazione permette di specificare diversi tipi di modelli (mockati come mock_emotion e mock_ticket) |
| Regole Personalizzate | Il RuleEngine applica regole complesse (es. basate su parole chiave e lunghezza del testo) per sovrascrivere la predizione |
| Pipeline Modulare | Sequenza configurabile di step - ogni cliente può definire una sequenza personalizzata di pre-processing, predizione, post-processing e applicazione regole |

## Come Eseguire il Codice Localmente

### Prerequisiti di Sistema

È necessario avere Python 3.8+ e pip installati sul sistema. Il progetto è stato testato su Windows, Linux e macOS.

### Installazione e Setup

Clonare il repository:

```bash
git clone https://github.com/Gyros4me/ai-os-architecture.git
cd ai-os-architecture/use-cases/UC04_Dynamic_Inference

# Installare le dipendenze necessarie
pip install -r requirements.txt
```

Questo installerà tutti i pacchetti Python necessari, tra cui FastAPI, Uvicorn, Pydantic e le librerie di testing.

### Esecuzione del Servizio API in Modalità Sviluppo

Avviare il server Uvicorn con il flag di reload per lo sviluppo:

```bash
uvicorn src.api:app --reload --host 127.0.0.1 --port 8000
```

Il servizio sarà immediatamente disponibile all'indirizzo http://127.0.0.1:8000. La documentazione interattiva delle API (Swagger UI) è accessibile all'indirizzo http://127.0.0.1:8000/docs.

### Esecuzione della Demo CLI da Linea di Comando

Per testare rapidamente i casi d'uso principali senza utilizzare l'API HTTP, è disponibile uno script demo:

```bash
python main.py
```

Questo eseguirà una serie di test predefiniti che dimostrano le funzionalità principali del sistema con entrambi i clienti configurati.

### Esecuzione dei Test

Per verificare la correttezza dell'implementazione e la copertura del codice:

```bash
pytest tests/ -v
```

## Clienti di Esempio e Scenari di Test

Il file di configurazione `config/clients.json` definisce due clienti di esempio che dimostrano diverse configurazioni e casi d'uso.

### Cliente A: Classificatore di Emozioni

**ID Cliente**: client_a

**Tipo Modello**: mock_emotion (classi supportate: CONTENTO, triste, alterato)

**Pipeline di Elaborazione**:
- Pre-processing: lowercase, strip_punctuation
- Post-processing: add_confidence_score
- Regole Business: Nessuna regola specifica

#### Scenari di Test per Cliente A

| Input di Test | Logica di Inferenza | Output Atteso |
|---------------|---------------------|---------------|
| "Sono così CONTENTO oggi!!!" | Pre-processing: "Sono così CONTENTO oggi" → Predizione (mock): "CONTENTO" → Post-processing: aggiunge confidence: 0.95 | `{'prediction': 'CONTENTO', 'confidence': 0.95, ...}` |
| "Sono così alterato!!!" | Pre-processing: "Sono così alterato" → Predizione (mock): "alterato" → Post-processing: aggiunge confidence: 0.95 | `{'prediction': 'alterato', 'confidence': 0.95, ...}` |

### Cliente B: Classificatore di Ticket con Regole Business

**ID Cliente**: client_b

**Tipo Modello**: mock_ticket (classi supportate: vendite, supporto, generic)

**Pipeline di Elaborazione**:
- Pre-processing: lowercase
- Regole Business:
  - **Regola Rimborso**: Se il testo contiene "rimborso" E la predizione è "vendite", sovrascrivi con "supporto"
  - **Regola Breve Generico**: Se il testo è breve (< 20 parole) E contiene "ciao" o "arrivederci" E la predizione è "generic", sovrascrivi con "support"

#### Scenari di Test per Cliente B

| Input di Test | Logica di Inferenza | Output Atteso |
|---------------|---------------------|---------------|
| "Ho bisogno di un rimborso per il mio acquisto." | 1. Pre-processing: "ho bisogno di un rimborso per il mio acquisto"<br>2. Predizione (mock): "vendite"<br>3. Regola 1 applicata (contiene "rimborso" e predizione è "vendite") → "supporto" | `{"prediction": "supporto", "client_id": "client_b", "processing_steps": ["lowercase", "mock_ticket", "rule_engine"], "rule_applied": "refund_rule"}` |
| "ciao, come va?" | 1. Pre-processing: "ciao, come va?"<br>2. Predizione (mock): "generic"<br>3. Regola 2 applicata (testo breve con "ciao" e predizione è "generic") → "support" | `{"prediction": "support", "client_id": "client_b", "processing_steps": ["lowercase", "mock_ticket", "rule_engine"], "rule_applied": "short_generic_rule"}` |
| "Voglio comprare un nuovo prodotto." | 1. Pre-processing: "voglio comprare un nuovo prodotto"<br>2. Predizione (mock): "vendite"<br>3. Nessuna regola applicata | `{"prediction": "vendite", "client_id": "client_b", "processing_steps": ["lowercase", "mock_ticket", "rule_engine"], "rule_applied": null}` |
| "Buongiorno, ho un problema con il servizio di assistenza tecnica." | 1. Pre-processing: "buongiorno, ho un problema con il servizio di assistenza tecnica"<br>2. Predizione (mock): "supporto"<br>3. Nessuna regola applicata | `{"prediction": "supporto", "client_id": "client_b", "processing_steps": ["lowercase", "mock_ticket", "rule_engine"], "rule_applied": null}` |

## Architettura Tecnica Dettagliata

### Flusso di Esecuzione

1. **Ricezione Richiesta**: L'API riceve una richiesta HTTP POST con client_id e text
2. **Caricamento Configurazione**: Il sistema carica la configurazione specifica per il client_id dal file clients.json
3. **Pipeline di Elaborazione**:
   - **Pre-processing**: Applica sequenzialmente tutte le funzioni di pre-processing configurate
   - **Predizione**: Passa il testo processato al modello specificato per ottenere una classificazione
   - **Post-processing**: Applica eventuali trasformazioni all'output della predizione
   - **Applicazione Regole**: Valuta e applica le regole business configurate che possono sovrascrivere la predizione
4. **Formattazione Risposta**: Struttura la risposta in formato JSON standardizzato
5. **Logging e Monitoring**: Registra metriche di esecuzione per debugging e monitoring

### Componenti Modulari

```
src/
├── api.py          # Endpoint FastAPI e gestione richieste HTTP
├── core.py         # Classe principale InferenceService
├── processors.py   # Funzioni di pre/post-processing
├── rules.py        # Motore di regole e regole specifiche
└── models.py       # Modelli Pydantic per input/output
```

## Struttura del Progetto

```
dynamic-inference-service/
├── config/                  # Configurazioni del sistema
│   └── clients.json         # Configurazione centralizzata dei clienti
├── src/                     # Codice sorgente principale
│   ├── __init__.py          # File di inizializzazione del package
│   ├── api.py               # Endpoint API FastAPI
│   ├── core.py              # Logica core del servizio di inferenza
│   ├── processors.py        # Implementazioni dei processori base
│   └── rules.py             # Implementazioni delle regole base
├── tests/                   # Suite di test
│   └── test_service.py      # Test unitari e di integrazione
├── .gitignore               # File da ignorare in Git
├── main.py                  # Script demo da linea di comando
├── README.md                # Questo file di documentazione
└── requirements.txt         # Dipendenze Python del progetto
```

## Note su Compromessi Progettuali e Lavoro Rimanente

### Compromessi e Assunzioni Progettuali

**Modelli Mockati**: Per mantenere un'implementazione minimale, riproducibile e autonoma, i modelli di classificazione sono attualmente mockati all'interno del modulo `src/core.py`. In un sistema di produzione reale, la funzione `_get_model_prediction` sarebbe sostituita con il caricamento dinamico di modelli ML reali (file .pkl, .h5, .onnx o connessione a servizi ML esterni).

**Caricamento Dinamico Semplificato**: Il caricamento dinamico dei processori è gestito tramite importlib con una logica relativamente semplice. Per un sistema di produzione con centinaia di processori, si potrebbe implementare un sistema di registrazione più sofisticato con validazione e caching.

**Validazione Schema Configurazione**: La validazione dello schema del file `clients.json` non è stata implementata come parte del core del sistema (sebbene menzionata come punto bonus). In ambiente di produzione, si raccomanda l'integrazione con librerie come Pydantic o Marshmallow per convalidare rigorosamente la struttura e i valori della configurazione all'avvio del servizio.

**Gestione Errori e Resilienza**: L'implementazione attuale include una gestione degli errori di base. Un sistema di produzione richiederebbe meccanismi più sofisticati per il retry, il fallback, il circuit breaking e il monitoring dettagliato.

### Roadmap di Sviluppo e Miglioramenti Futuri

1. **Implementazione Modelli ML Reali**: Sostituire la logica di mock in `_get_model_prediction` con il caricamento dinamico di modelli ML reali da diverse sorgenti (file system, registri modello, servizi esterni)

2. **Validazione Configurazione con Pydantic**: Implementare classi Pydantic per la validazione dello schema di `clients.json`, garantendo type safety e validazione dei valori all'avvio del servizio

3. **Caching e Ottimizzazione Performance**: Implementare caching multi-livello per modelli, processori e configurazioni per evitare ricaricamenti costosi ad ogni richiesta, migliorando significativamente le prestazioni e riducendo la latenza

4. **Sistema di Versioning Modelli**: Estendere la logica di caricamento per supportare versioni multiple dello stesso modello per un singolo cliente, abilitando A/B testing, rollout graduali e rollback

5. **Monitoring e Observability**: Integrare strumenti di monitoring (Prometheus, Grafana) e logging strutturato per tracciare metriche di performance, utilizzo e errori in tempo reale

6. **Containerizzazione e Orchestrazione**: Fornire Dockerfile e configurazioni Kubernetes per il deployment in ambienti containerizzati e orchestrati

7. **Autenticazione e Autorizzazione**: Aggiungere meccanismi di autenticazione (JWT, OAuth) e autorizzazione per proteggere gli endpoint API e garantire l'accesso solo ai clienti autorizzati

8. **Estensibilità Avanzata**: Implementare un sistema plugin più sofisticato che permetta ai clienti di caricare i propri processori e regole personalizzati senza modificare il codice core del servizio

## Licenza

Questo progetto è distribuito sotto licenza MIT. Per i dettagli completi, consultare il file LICENSE.txt incluso nel repository.
 
