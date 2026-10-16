"""
Semantic Embedder Service
=========================

Wrapper ottimizzato per sentence-transformers con:
- Model lazy loading e caching
- Batch processing efficiente
- Performance monitoring
- Support per CPU e GPU

Autore: Alessandro
Modello: sentence-transformers/all-MiniLM-L6-v2
Performance: ~2000 docs/sec su CPU, 80MB memory footprint
"""

from sentence_transformers import SentenceTransformer
from typing import List, Union, Optional
import numpy as np
from functools import lru_cache
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class SemanticEmbedder:
    """
    Production-ready semantic embedder con caching e monitoring.
    
    Features:
    - Lazy loading: modello caricato solo al primo utilizzo
    - Batch optimization: processa documenti in batch per performance
    - Cache: query ripetute usano cache LRU
    - Metrics: tracking performance per monitoring
    
    Example:
        >>> embedder = SemanticEmbedder()
        >>> embedding = embedder.embed_single("L'AI trasforma il mondo")
        >>> print(embedding.shape)
        (384,)
        
        >>> texts = ["Doc 1", "Doc 2", "Doc 3"]
        >>> embeddings = embedder.embed_batch(texts)
        >>> print(embeddings.shape)
        (3, 384)
    """
    
    # Modelli consigliati con caratteristiche
    RECOMMENDED_MODELS = {
        "all-MiniLM-L6-v2": {
            "dimensions": 384,
            "speed": "fast",  # ~2000 docs/sec CPU
            "size": "80MB",
            "best_for": "production, low-latency"
        },
        "all-mpnet-base-v2": {
            "dimensions": 768,
            "speed": "medium",  # ~500 docs/sec CPU
            "size": "420MB",
            "best_for": "maximum quality"
        },
        "paraphrase-multilingual-MiniLM-L12-v2": {
            "dimensions": 384,
            "speed": "fast",
            "size": "220MB",
            "best_for": "multilingual support"
        }
    }
    
    def __init__(
        self, 
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: Optional[str] = None,
        cache_folder: Optional[str] = None
    ):
        """
        Inizializza embedder con lazy loading.
        
        Args:
            model_name: Nome modello HuggingFace (default: all-MiniLM-L6-v2)
            device: 'cpu', 'cuda', 'mps' o None (auto-detect)
            cache_folder: Path per cache modelli (default: ~/.cache/torch)
        
        Note:
            Il modello NON viene caricato subito ma al primo utilizzo (lazy loading)
        """
        self.model_name = model_name
        self.device = device or self._detect_device()
        self.cache_folder = cache_folder
        
        # Lazy loading: modello inizializzato a None
        self._model = None
        
        # Metrics tracking
        self.metrics = {
            "total_embeddings_generated": 0,
            "total_time_spent": 0.0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        logger.info(
            f"SemanticEmbedder initialized - Model: {model_name}, Device: {self.device}"
        )
    
    @staticmethod
    def _detect_device() -> str:
        """Auto-detect best available device"""
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            elif torch.backends.mps.is_available():  # Apple Silicon
                return "mps"
        except ImportError:
            pass
        return "cpu"
    
    @property
    def model(self) -> SentenceTransformer:
        """
        Lazy load del modello (carica solo al primo accesso).
        
        Returns:
            SentenceTransformer: Modello pronto all'uso
        """
        if self._model is None:
            logger.info(f"Loading model '{self.model_name}' on device '{self.device}'...")
            start_time = time.time()
            
            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
                cache_folder=self.cache_folder
            )
            
            load_time = time.time() - start_time
            logger.info(
                f"Model loaded successfully in {load_time:.2f}s "
                f"(dimension: {self._model.get_sentence_embedding_dimension()})"
            )
        
        return self._model
    
    def embed_single(self, text: str) -> np.ndarray:
        """
        Genera embedding per un singolo testo.
        
        Args:
            text: Stringa di testo da embeddare
            
        Returns:
            np.ndarray: Vettore embedding (shape: [embedding_dim])
            
        Example:
            >>> embedder = SemanticEmbedder()
            >>> vec = embedder.embed_single("Hello world")
            >>> vec.shape
            (384,)
        """
        start_time = time.time()
        
        embedding = self.model.encode(
            text, 
            convert_to_numpy=True,
            show_progress_bar=False
        )
        
        # Update metrics
        elapsed = time.time() - start_time
        self.metrics["total_embeddings_generated"] += 1
        self.metrics["total_time_spent"] += elapsed
        
        return embedding
    
    def embed_batch(
        self, 
        texts: List[str], 
        batch_size: int = 32,
        show_progress: bool = False,
        normalize: bool = False
    ) -> np.ndarray:
        """
        Genera embeddings per batch di testi (OTTIMIZZATO).
        
        Args:
            texts: Lista di stringhe da embeddare
            batch_size: Dimensione batch (32 ottimale CPU, 128 per GPU)
            show_progress: Mostra progress bar (utile per batch grandi)
            normalize: Normalizza vettori a lunghezza unitaria (per cosine similarity)
            
        Returns:
            np.ndarray: Matrice embeddings (shape: [num_texts, embedding_dim])
            
        Performance:
            - CPU (all-MiniLM-L6-v2): ~2000 docs/sec
            - GPU (all-MiniLM-L6-v2): ~8000 docs/sec
            
        Example:
            >>> texts = ["Doc 1", "Doc 2", "Doc 3"]
            >>> embeddings = embedder.embed_batch(texts, batch_size=32)
            >>> embeddings.shape
            (3, 384)
        """
        if not texts:
            logger.warning("Empty text list provided to embed_batch")
            return np.array([])
        
        start_time = time.time()
        
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
            normalize_embeddings=normalize
        )
        
        # Update metrics
        elapsed = time.time() - start_time
        self.metrics["total_embeddings_generated"] += len(texts)
        self.metrics["total_time_spent"] += elapsed
        
        logger.debug(
            f"Batch embedding completed: {len(texts)} texts in {elapsed:.2f}s "
            f"({len(texts)/elapsed:.0f} docs/sec)"
        )
        
        return embeddings
    
    @lru_cache(maxsize=1000)
    def embed_cached(self, text: str) -> tuple:
        """
        Embedding con cache LRU per query ripetute.
        
        Utile per query frequenti in search. Cache mantiene ultimi 1000 risultati.
        
        Args:
            text: Testo da embeddare
            
        Returns:
            tuple: Embedding come tupla (per compatibilità cache)
            
        Note:
            Ritorna tupla invece di np.ndarray perché LRU cache richiede hashable types
        """
        self.metrics["cache_misses"] += 1
        embedding = self.embed_single(text)
        return tuple(embedding.tolist())
    
    def embed_with_cache_check(self, text: str) -> np.ndarray:
        """
        Wrapper che traccia cache hits/misses.
        
        Args:
            text: Testo da embeddare
            
        Returns:
            np.ndarray: Embedding vector
        """
        # Check se in cache
        cache_info = self.embed_cached.cache_info()
        initial_hits = cache_info.hits
        
        # Get embedding (da cache o nuovo)
        embedding_tuple = self.embed_cached(text)
        
        # Check se era in cache
        cache_info = self.embed_cached.cache_info()
        if cache_info.hits > initial_hits:
            self.metrics["cache_hits"] += 1
        
        return np.array(embedding_tuple)
    
    def get_model_info(self) -> dict:
        """
        Ritorna metadata del modello per monitoring e debugging.
        
        Returns:
            dict: Informazioni modello, device, performance
            
        Example:
            >>> info = embedder.get_model_info()
            >>> print(info)
            {
                'model_name': 'sentence-transformers/all-MiniLM-L6-v2',
                'embedding_dimension': 384,
                'max_seq_length': 256,
                'device': 'cpu',
                'model_loaded': True,
                'total_embeddings': 1500,
                'avg_time_per_embedding': 0.0005,
                'cache_hit_rate': 0.23
            }
        """
        info = {
            "model_name": self.model_name,
            "device": str(self.device),
            "model_loaded": self._model is not None,
        }
        
        # Info dettagliate solo se modello caricato
        if self._model is not None:
            info.update({
                "embedding_dimension": self.model.get_sentence_embedding_dimension(),
                "max_seq_length": self.model.max_seq_length,
                "tokenizer": self.model.tokenizer.__class__.__name__
            })
        
        # Aggiungi metrics
        total_embeddings = self.metrics["total_embeddings_generated"]
        if total_embeddings > 0:
            info.update({
                "total_embeddings_generated": total_embeddings,
                "total_time_spent_seconds": round(self.metrics["total_time_spent"], 2),
                "avg_time_per_embedding_ms": round(
                    (self.metrics["total_time_spent"] / total_embeddings) * 1000, 2
                ),
                "throughput_docs_per_sec": round(
                    total_embeddings / self.metrics["total_time_spent"], 0
                )
            })
        
        # Cache statistics
        cache_info = self.embed_cached.cache_info()
        total_cache_calls = cache_info.hits + cache_info.misses
        if total_cache_calls > 0:
            info.update({
                "cache_size": cache_info.currsize,
                "cache_hits": cache_info.hits,
                "cache_misses": cache_info.misses,
                "cache_hit_rate": round(cache_info.hits / total_cache_calls, 2)
            })
        
        return info
    
    def clear_cache(self):
        """Pulisce cache LRU"""
        self.embed_cached.cache_clear()
        logger.info("Embedding cache cleared")
    
    def __repr__(self) -> str:
        return (
            f"SemanticEmbedder(model='{self.model_name}', "
            f"device='{self.device}', loaded={self._model is not None})"
        )


class EmbeddingBenchmark:
    """
    Utility class per benchmarking e confronto modelli.
    
    Usage:
        >>> benchmark = EmbeddingBenchmark()
        >>> results = benchmark.compare_models(
        ...     ["all-MiniLM-L6-v2", "all-mpnet-base-v2"],
        ...     sample_texts=["test"] * 100
        ... )
    """
    
    @staticmethod
    def benchmark_model(
        model_name: str,
        test_texts: List[str],
        iterations: int = 3,
        batch_size: int = 32
    ) -> dict:
        """
        Benchmark performance di un modello.
        
        Args:
            model_name: Nome modello da testare
            test_texts: Lista testi per test
            iterations: Numero ripetizioni per media
            batch_size: Dimensione batch
            
        Returns:
            dict: Metriche performance
            
        Example:
            >>> texts = ["Sample text"] * 100
            >>> results = EmbeddingBenchmark.benchmark_model(
            ...     "sentence-transformers/all-MiniLM-L6-v2",
            ...     texts,
            ...     iterations=3
            ... )
            >>> print(results)
            {
                'model': 'sentence-transformers/all-MiniLM-L6-v2',
                'num_documents': 100,
                'iterations': 3,
                'avg_time_seconds': 0.05,
                'throughput_docs_per_sec': 2000,
                'time_per_doc_ms': 0.5,
                'batch_size': 32
            }
        """
        logger.info(f"Benchmarking model: {model_name}")
        
        # Initialize embedder
        embedder = SemanticEmbedder(model_name)
        
        # Warmup (primo run spesso più lento per loading)
        _ = embedder.embed_batch(test_texts[:10], batch_size=batch_size)
        
        # Actual benchmark
        times = []
        for i in range(iterations):
            start = time.time()
            _ = embedder.embed_batch(test_texts, batch_size=batch_size)
            elapsed = time.time() - start
            times.append(elapsed)
            logger.debug(f"Iteration {i+1}/{iterations}: {elapsed:.3f}s")
        
        # Calculate statistics
        avg_time = np.mean(times)
        std_time = np.std(times)
        throughput = len(test_texts) / avg_time
        time_per_doc = (avg_time / len(test_texts)) * 1000  # ms
        
        results = {
            "model": model_name,
            "num_documents": len(test_texts),
            "iterations": iterations,
            "avg_time_seconds": round(avg_time, 3),
            "std_time_seconds": round(std_time, 3),
            "throughput_docs_per_sec": round(throughput, 0),
            "time_per_doc_ms": round(time_per_doc, 2),
            "batch_size": batch_size,
            "device": embedder.device
        }
        
        logger.info(
            f"Benchmark completed: {throughput:.0f} docs/sec "
            f"({time_per_doc:.2f}ms per doc)"
        )
        
        return results
    
    @staticmethod
    def compare_models(
        model_names: List[str],
        sample_texts: List[str],
        iterations: int = 3
    ) -> List[dict]:
        """
        Confronta performance di multipli modelli.
        
        Args:
            model_names: Lista nomi modelli
            sample_texts: Testi per test
            iterations: Ripetizioni
            
        Returns:
            List[dict]: Risultati per ogni modello
        """
        results = []
        
        for model_name in model_names:
            try:
                result = EmbeddingBenchmark.benchmark_model(
                    model_name, 
                    sample_texts, 
                    iterations
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to benchmark {model_name}: {e}")
                results.append({
                    "model": model_name,
                    "error": str(e)
                })
        
        return results
    
    @staticmethod
    def print_comparison_table(results: List[dict]):
        """
        Stampa tabella comparativa risultati.
        
        Args:
            results: Output di compare_models()
        """
        print("\n" + "="*80)
        print("EMBEDDING MODEL PERFORMANCE COMPARISON")
        print("="*80)
        print(f"{'Model':<40} {'Throughput':<15} {'Latency':<15}")
        print("-"*80)
        
        for result in results:
            if "error" in result:
                print(f"{result['model']:<40} ERROR: {result['error']}")
            else:
                throughput = f"{result['throughput_docs_per_sec']:.0f} docs/sec"
                latency = f"{result['time_per_doc_ms']:.2f} ms/doc"
                print(f"{result['model']:<40} {throughput:<15} {latency:<15}")
        
        print("="*80 + "\n")


# Convenience function per quick usage
def get_default_embedder() -> SemanticEmbedder:
    """
    Ritorna embedder con configurazione default ottimizzata.
    
    Returns:
        SemanticEmbedder: Embedder pronto all'uso
        
    Example:
        >>> from src.services.embedder import get_default_embedder
        >>> embedder = get_default_embedder()
        >>> embedding = embedder.embed_single("Test text")
    """
    return SemanticEmbedder(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)
    
    embedder = SemanticEmbedder()
    
    # Test single
    text = "L'intelligenza artificiale sta trasformando il mondo"
    embedding = embedder.embed_single(text)
    print(f"Single embedding shape: {embedding.shape}")
    
    # Test batch
    texts = [
        "Machine learning per analisi predittiva",
        "Deep learning e reti neurali",
        "Natural language processing avanzato"
    ] * 10  # 30 docs
    
    embeddings = embedder.embed_batch(texts, show_progress=True)
    print(f"Batch embeddings shape: {embeddings.shape}")
    
    # Print info
    info = embedder.get_model_info()
    print("\nModel Info:")
    for key, value in info.items():
        print(f"  {key}: {value}")