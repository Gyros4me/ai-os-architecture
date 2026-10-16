# Use Cases

Reference use cases for the AI-OS architecture. Two kinds of material live here: architecture studies (PDF) and runnable reference implementations (code).

## Architecture studies

| ID | Title | Format |
|----|-------|--------|
| UC01 | [Media Events Surveillance](UC01_Media_Events_Surveillance.pdf) | PDF |
| UC02 | [Drone Detection v2.0](UC02_Drone_Detection_v2.0.pdf) | PDF |
| UC03 | [Space Computing](UC03_Space_Computing.pdf) | PDF |

## Reference implementations

| ID | Title | Description |
|----|-------|-------------|
| UC04 | [Dynamic Inference](UC04_Dynamic_Inference/) | Per-client, runtime-configurable inference service (dynamic processors, rule engine, FastAPI) |
| UC05 | [Agentic Search](UC05_Agentic_Search/) | Conversational search agent with hybrid fuzzy + semantic retrieval (reference domain: books catalog) |
| UC06 | [Vector Ingestion](UC06_Vector_Ingestion/) | Dockerized ingestion and vector-store service (FastAPI, ChromaDB, all-MiniLM-L6-v2), orchestrated by n8n; Tier-0 retrieval locally, Tier-2 generation on a Magellano server with MiniLM-only fallback |

New code use cases follow the `UCNN_Name/` folder convention; PDFs stay at the top level.
