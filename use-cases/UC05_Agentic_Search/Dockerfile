FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ src/
COPY demo.py .
COPY benchmark.py .

# Copy sample data (or mount volume in production)
COPY data/ data/

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run API server
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
