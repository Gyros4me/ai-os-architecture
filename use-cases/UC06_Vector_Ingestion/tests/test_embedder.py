"""
Test Suite per SemanticEmbedder
================================

Test coverage per:
- Embedding generation
- Batch processing
- Cache behavior
- Performance benchmarking

Run: pytest tests/test_embedder.py -v
"""

import pytest
import numpy as np
import sys
from pathlib import Path

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.embedder import SemanticEmbedder, EmbeddingBenchmark


class TestSemanticEmbedder:
    """Test suite per SemanticEmbedder"""
    
    @pytest.fixture
    def embedder(self):
        """Fixture: embedder instance"""
        return SemanticEmbedder()
    
    def test_initialization(self, embedder):
        """Test: embedder si inizializza correttamente"""
        assert embedder.model_name == "sentence-transformers/all-MiniLM-L6-v2"
        assert embedder.device in ["cpu", "cuda", "mps"]
        assert embedder._model is None  # Lazy loading non ancora attivato
    
    def test_lazy_loading(self, embedder):
        """Test: modello carica solo al primo utilizzo"""
        assert embedder._model is None
        
        # Trigger lazy load
        _ = embedder.model
        
        assert embedder._model is not None
    
    def test_embed_single(self, embedder):
        """Test: embedding singolo testo"""
        text = "L'intelligenza artificiale sta trasformando il mondo"
        embedding = embedder.embed_single(text)
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (384,)  # all-MiniLM-L6-v2 dimension
        assert embedder.metrics["total_embeddings_generated"] == 1
    
    def test_embed_batch(self, embedder):
        """Test: embedding batch di testi"""
        texts = [
            "Machine learning per analisi predittiva",
            "Deep learning e reti neurali",
            "Natural language processing"
        ]
        
        embeddings = embedder.embed_batch(texts, batch_size=2)
        
        assert embeddings.shape == (3, 384)
        assert embedder.metrics["total_embeddings_generated"] == 3
    
    def test_embed_empty_batch(self, embedder):
        """Test: batch vuoto ritorna array vuoto"""
        embeddings = embedder.embed_batch([])
        assert embeddings.shape == (0,)
    
    def test_cache_behavior(self, embedder):
        """Test: cache LRU funziona correttamente"""
        text = "Test caching"
        
        # First call: cache miss
        emb1 = embedder.embed_with_cache_check(text)
        cache_info_1 = embedder.embed_cached.cache_info()
        
        # Second call: cache hit
        emb2 = embedder.embed_with_cache_check(text)
        cache_info_2 = embedder.embed_cached.cache_info()
        
        # Verify cache hit
        assert cache_info_2.hits > cache_info_1.hits
        
        # Verify embeddings are identical
        np.testing.assert_array_equal(emb1, emb2)
    
    def test_get_model_info(self, embedder):
        """Test: model info contiene campi attesi"""
        # Trigger model loading
        _ = embedder.embed_single("test")
        
        info = embedder.get_model_info()
        
        assert "model_name" in info
        assert "embedding_dimension" in info
        assert info["embedding_dimension"] == 384
        assert "device" in info
        assert "total_embeddings_generated" in info
    
    def test_semantic_similarity(self, embedder):
        """Test: testi simili hanno embeddings vicini"""
        text1 = "Il cane mangia"
        text2 = "Il cane sta mangiando"
        text3 = "La matematica Ã¨ difficile"
        
        emb1 = embedder.embed_single(text1)
        emb2 = embedder.embed_single(text2)
        emb3 = embedder.embed_single(text3)
        
        # Cosine similarity
        def cosine_sim(a, b):
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        
        sim_12 = cosine_sim(emb1, emb2)
        sim_13 = cosine_sim(emb1, emb3)
        
        # text1 e text2 dovrebbero essere piÃ¹ simili di text1 e text3
        assert sim_12 > sim_13
        assert sim_12 > 0.7  # Alta similarity


class TestEmbeddingBenchmark:
    """Test suite per benchmark utilities"""
    
    def test_benchmark_model(self):
        """Test: benchmark ritorna metriche valide"""
        texts = ["Test document"] * 50
        
        results = EmbeddingBenchmark.benchmark_model(
            "sentence-transformers/all-MiniLM-L6-v2",
            texts,
            iterations=2
        )
        
        assert "model" in results
        assert "throughput_docs_per_sec" in results
        assert "avg_time_seconds" in results
        assert results["num_documents"] == 50
        assert results["throughput_docs_per_sec"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])