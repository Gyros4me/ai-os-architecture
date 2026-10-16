"""
Pydantic schemas per API validation
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class TextIngestionRequest(BaseModel):
    id: str
    text: str
    metadata: Optional[Dict[str, Any]] = {}

class ChunkResponse(BaseModel):
    id: str
    content: str
    metadata: Dict[str, Any]
    timestamp: datetime

class IngestionResponse(BaseModel):
    message: str
    source: str
    chunks_count: int
    chunk_ids: List[str]

class UpdateChunkRequest(BaseModel):
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class QueryRequest(BaseModel):
    query: str
    n_results: int = 5
    where: Optional[Dict[str, Any]] = None

class TextUploadRequest(BaseModel):
    """Schema per /upload/text"""
    content: str = Field(..., min_length=1, max_length=1000000)
    source_id: Optional[str] = None
    chunk_size: int = Field(1000, ge=10, le=10000)
    chunk_overlap: int = Field(100, ge=0, le=1000)
    batch_size: int = Field(50, ge=1, le=100)
    metadata: Optional[Dict[str, Any]] = {}

class PDFUploadRequest(BaseModel):
    """Schema per /upload/pdf"""
    chunk_size: int = Field(1000, ge=10, le=10000)
    chunk_overlap: int = Field(100, ge=0, le=1000)
    batch_size: int = Field(50, ge=1, le=100)

class CSVUploadRequest(BaseModel):
    """Schema per /upload/csv"""
    group_by: Optional[str] = None
    max_rows_per_chunk: int = Field(50, ge=1, le=1000)
    batch_size: int = Field(50, ge=1, le=100)

class SearchRequest(BaseModel):
    """Schema per /search"""
    query: str = Field(..., min_length=1, max_length=1000)
    n_results: int = Field(5, ge=1, le=100)
    source_filter: Optional[str] = None
    min_similarity: float = Field(0.0, ge=0.0, le=1.0)
    include_metadata: bool = True

class DLQRetryRequest(BaseModel):
    """Schema per /dlq/retry"""
    force_retry: bool = False

class DLQTestRequest(BaseModel):
    """Schema per /dlq/test-failure"""
    simulate_error: Optional[str] = "test_error"
    make_permanent: bool = False
    chunk_data: Optional[Dict[str, Any]] = None

class EmbeddingBatchRequest(BaseModel):
    """Schema per /embeddings/batch"""
    texts: List[str] = Field(..., min_items=1, max_items=1000)
    normalize: bool = False
    batch_size: int = Field(32, ge=1, le=256)

class BatchUploadResult(BaseModel):
    """Risultato per singolo file in /upload/batch"""
    filename: str
    status: str  # "success" | "error"
    chunks_processed: Optional[int] = None
    error: Optional[str] = None
    processing_time_ms: float

class BatchUploadResponse(BaseModel):
    """Risposta aggregata di /upload/batch"""
    total_files: int
    successful: int
    failed: int
    total_chunks: int
    results: List[BatchUploadResult]
    processing_time_ms: float
    timestamp: str