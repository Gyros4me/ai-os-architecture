FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Crea struttura directory serbatoio
RUN mkdir -p /reservoir/{00_queue,01_ingesting,02_reservoir/{by_source,by_domain,by_year},03_embeddings,04_failed,config}

ENV SCIENTIFIC_RESERVOIR=/reservoir
ENV VECTOR_SERVICE_URL=http://vector-service:8000
ENV MAGELLANO_SERVICE_URL=http://magellano-service:8004

# Copia config di default se non montata esternamente
CMD ["sh", "-c", "\
  if [ ! -f /reservoir/config/keywords.yml ]; then \
    cp /app/config/keywords.yml /reservoir/config/keywords.yml; \
  fi && \
  python /app/src/fetcher.py full \
"]
