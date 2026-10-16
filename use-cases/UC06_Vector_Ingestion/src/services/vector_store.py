"""
Vector Store Service con Support per Custom Embedder
====================================================

Estende ChromaDB con:
- Support per semantic embedder custom
- Backward compatibility con default embedder
- Batch operations ottimizzate
- Error handling robusto

Modificato da: Alessandro
"""

import chromadb
from chromadb.utils import embedding_functions
from typing import List, Dict, Any, Optional, Union
import os
import logging
import uuid
from datetime import datetime

# Import del nostro embedder custom
from .embedder import SemanticEmbedder, get_default_embedder

logger = logging.getLogger(__name__)


class VectorStoreService:
    """
    Service per gestione vector store con embeddings semantici.
    
    Features:
    - Custom embedder ottimizzato (all-MiniLM-L6-v2) o ChromaDB default
    - Batch operations per performance
    - Retry logic per resilienza
    - Query con filtering metadata
    - Supporto per ChromaDB HTTP client o Persistent client
    
    Example:
        >>> # Con custom embedder (RACCOMANDATO)
        >>> embedder = SemanticEmbedder()
        >>> vector_store = VectorStoreService(embedder=embedder)
        >>> 
        >>> # Con default ChromaDB
        >>> vector_store = VectorStoreService(use_custom_embedder=False)
    """
    
    def __init__(
        self,
        collection_name: str = "document_chunks",
        db_path: Optional[str] = None,
        chroma_server_host: Optional[str] = None,
        chroma_server_port: Optional[int] = None,
        embedder: Optional[SemanticEmbedder] = None,
        use_custom_embedder: bool = True
    ):
        """
        Inizializza vector store service.
        
        Args:
            collection_name: Nome della collection ChromaDB
            db_path: Path per persistenza ChromaDB (se None, usa client HTTP)
            chroma_server_host: Host del server ChromaDB (solo per client HTTP)
            chroma_server_port: Porta del server ChromaDB (solo per client HTTP)
            embedder: Custom embedder (None = crea default)
            use_custom_embedder: Se True, usa SemanticEmbedder ottimizzato
        """
        self.collection_name = collection_name
        self.use_custom_embedder = use_custom_embedder
        self._reranker = None
        self.reranker_model_name = os.getenv(
            "RERANKER_MODEL",
            "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )
        
        # Initialize ChromaDB client
        self.client = self._initialize_chroma_client(
            db_path, chroma_server_host, chroma_server_port
        )
        
        # SCELTA EMBEDDER: Custom vs Default
        if use_custom_embedder:
            if embedder is None:
                # Crea default optimized embedder
                self.embedder = get_default_embedder()
                logger.info(f"Using default optimized SemanticEmbedder: {self.embedder.model_name}")
            else:
                self.embedder = embedder
                logger.info(f"Using provided custom embedder: {embedder.model_name}")
            
            # Con custom embedder: NON passiamo embedding_function a ChromaDB
            # Genereremo embeddings manualmente
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={
                    "hnsw:space": "cosine",
                    "description": "Vector store for document chunks with semantic embeddings",
                    "created_at": datetime.now().isoformat(),
                    "embedder": self.embedder.model_name
                }
            )
        else:
            # Fallback a ChromaDB default embedder
            self.embedder = None
            self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
            logger.info("Using ChromaDB DefaultEmbeddingFunction")
            
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                embedding_function=self.embedding_fn,
                metadata={
                    "hnsw:space": "cosine",
                    "description": "Vector store for document chunks with ChromaDB default embeddings",
                    "created_at": datetime.now().isoformat(),
                    "embedder": "chromadb_default"
                }
            )
        
        logger.info(f"VectorStoreService initialized - Collection: {self.collection.name}")
    
    def _initialize_chroma_client(
        self,
        db_path: Optional[str],
        chroma_server_host: Optional[str],
        chroma_server_port: Optional[int]
    ) -> Union[chromadb.PersistentClient, chromadb.HttpClient]:
        """
        Inizializza il client ChromaDB appropriato in base ai parametri.
        
        Priorità:
        1. Se db_path specificato: PersistentClient
        2. Se host/port specificati: HttpClient
        3. Altrimenti: PersistentClient con path di default
        
        Args:
            db_path: Path per persistenza locale
            chroma_server_host: Host server ChromaDB
            chroma_server_port: Porta server ChromaDB
            
        Returns:
            Client ChromaDB configurato
        """
        try:
            if db_path:
                # Usa PersistentClient per storage locale
                os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else db_path, exist_ok=True)
                client = chromadb.PersistentClient(path=db_path)
                logger.info(f"Initialized PersistentClient at: {db_path}")
                return client
            elif chroma_server_host and chroma_server_port:
                # Usa HttpClient per server remoto
                client = chromadb.HttpClient(
                    host=chroma_server_host,
                    port=chroma_server_port
                )
                logger.info(f"Initialized HttpClient for: {chroma_server_host}:{chroma_server_port}")
                return client
            else:
                # Default: PersistentClient in percorso predefinito
                default_path = "./data/chroma_db"
                os.makedirs(default_path, exist_ok=True)
                client = chromadb.PersistentClient(path=default_path)
                logger.info(f"Initialized default PersistentClient at: {default_path}")
                return client
                
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB client: {e}")
            raise
    
    def add_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggiunge chunks al vector store (singola operazione).
        
        Args:
            chunks: Lista di dict con 'id', 'content', 'metadata'
            
        Returns:
            Dict con risultato operazione
            
        Example:
            >>> chunks = [
            ...     {
            ...         "id": "chunk_1",
            ...         "content": "Testo del documento",
            ...         "metadata": {"source": "doc.pdf", "page": 1}
            ...     }
            ... ]
            >>> result = vector_store.add_chunks(chunks)
        """
        if not chunks:
            logger.warning("Empty chunks list provided to add_chunks")
            return {"status": "error", "message": "Empty chunks list"}
        
        try:
            # Prepara dati
            ids = [c.get('id', str(uuid.uuid4())) for c in chunks]
            documents = [c['content'] for c in chunks]
            metadatas = [c.get('metadata', {}) for c in chunks]
            
            # Aggiungi timestamp ai metadata se non presente
            for metadata in metadatas:
                if 'created_at' not in metadata:
                    metadata['created_at'] = datetime.now().isoformat()
            
            if self.embedder:
                # Custom embedder: genera embeddings in batch
                logger.debug(f"Generating embeddings for {len(documents)} chunks...")
                embeddings = self.embedder.embed_batch(
                    documents,
                    batch_size=32
                ).tolist()
                
                # Add con embeddings pre-calcolati
                self.collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                    embeddings=embeddings
                )
                
                logger.info(f"Added {len(chunks)} chunks with custom embeddings")
                return {
                    "status": "success",
                    "chunks_added": len(chunks),
                    "embedder": self.embedder.model_name
                }
            else:
                # ChromaDB default: genera embeddings automaticamente
                self.collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas
                )
                
                logger.info(f"Added {len(chunks)} chunks with default embeddings")
                return {
                    "status": "success",
                    "chunks_added": len(chunks),
                    "embedder": "chromadb_default"
                }
                
        except Exception as e:
            logger.error(f"Error adding chunks: {e}")
            return {
                "status": "error",
                "message": str(e),
                "chunks_added": 0
            }
    
    def add_chunks_batch(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> Dict[str, Any]:
        """
        Aggiunge chunks in batch per performance ottimali.
        
        Per file grandi (1000+ chunks), splitting in batch previene:
        - Timeout requests
        - Memory overflow
        - Permette progress tracking
        
        Args:
            chunks: Lista chunks da aggiungere
            batch_size: Dimensione batch (default 100)
            
        Returns:
            Dict con statistiche e risultati batch
            
        Example:
            >>> # File grande: 1000 chunks
            >>> result = vector_store.add_chunks_batch(chunks, batch_size=100)
            # Esegue 10 batch da 100 chunks ciascuno
        """
        if not chunks:
            logger.warning("Empty chunks list provided to add_chunks_batch")
            return {
                "status": "error",
                "message": "Empty chunks list",
                "total_chunks": 0
            }
        
        total_chunks = len(chunks)
        total_batches = (total_chunks + batch_size - 1) // batch_size
        
        logger.info(f"Starting batch ingestion: {total_chunks} chunks, {total_batches} batches")
        
        successful_chunks = 0
        failed_chunks = []
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, total_chunks)
            batch = chunks[start_idx:end_idx]
            
            try:
                logger.debug(f"Processing batch {batch_idx + 1}/{total_batches} ({len(batch)} chunks)")
                result = self.add_chunks(batch)
                
                if result.get("status") == "success":
                    successful_chunks += len(batch)
                else:
                    # Batch fallito, tenta individuale
                    for chunk in batch:
                        try:
                            self.add_chunks([chunk])
                            successful_chunks += 1
                        except Exception as e:
                            failed_chunks.append({
                                "chunk_id": chunk.get('id', 'unknown'),
                                "error": str(e)
                            })
                            
            except Exception as e:
                logger.error(f"Batch {batch_idx + 1} failed: {e}")
                # Aggiungi tutti i chunk del batch come falliti
                for chunk in batch:
                    failed_chunks.append({
                        "chunk_id": chunk.get('id', 'unknown'),
                        "error": str(e)
                    })
        
        # Preparazione risultato
        result = {
            "status": "success" if len(failed_chunks) == 0 else "partial_success",
            "total_chunks": total_chunks,
            "successful_chunks": successful_chunks,
            "failed_chunks": len(failed_chunks),
            "batches_processed": total_batches,
            "batch_size": batch_size
        }
        
        if failed_chunks:
            result["errors"] = failed_chunks[:10]  # Limita a 10 errori per non sovraccaricare
            if len(failed_chunks) > 10:
                result["error_summary"] = f"{len(failed_chunks) - 10} more errors not shown"
        
        logger.info(
            f"Batch ingestion completed: {successful_chunks}/{total_chunks} chunks succeeded"
        )
        
        return result
    
    def get_chunk(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        Recupera chunk singolo per ID.
        
        Args:
            chunk_id: ID univoco chunk
            
        Returns:
            dict con 'id', 'content', 'metadata' o None se non trovato
        """
        try:
            result = self.collection.get(ids=[chunk_id])
            
            if result['ids']:
                return {
                    "id": result['ids'][0],
                    "content": result['documents'][0],
                    "metadata": result['metadatas'][0]
                }
            
            logger.debug(f"Chunk {chunk_id} not found")
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving chunk {chunk_id}: {e}")
            return None
    
    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict] = None,
        include_metadata: bool = True,
        min_similarity: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Ricerca semantica nel vector store.
        
        Args:
            query_text: Testo query
            n_results: Numero risultati da ritornare
            where: Filtro metadata (es. {"source": "doc.pdf"})
            include_metadata: Se includere i metadati nei risultati
            min_similarity: Soglia minima cosine similarity normalizzata [0, 1]
            
        Returns:
            Lista risultati ordinati per similarity
            
        Example:
            >>> # Ricerca semplice
            >>> results = vector_store.query("intelligenza artificiale", n_results=5)
            >>> 
            >>> # Ricerca con filtro
            >>> results = vector_store.query(
            ...     "AI applications",
            ...     n_results=10,
            ...     where={"type": "pdf", "page": {"$gte": 5}}
            ... )
        """
        try:
            # Configura cosa includere in base a include_metadata
            if include_metadata:
                include = ['documents', 'metadatas', 'distances']
            else:
                include = ['documents', 'distances']
            
            if self.embedder:
                # Custom embedder: genera query embedding (usa cache per query ripetute)
                logger.debug(f"Generating query embedding for: '{query_text[:50]}...'")
                query_embedding = list(self.embedder.embed_cached(query_text))
                
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    where=where,
                    include=include
                )
            else:
                # Default embedder: ChromaDB genera automaticamente
                results = self.collection.query(
                    query_texts=[query_text],
                    n_results=n_results,
                    where=where,
                    include=include
                )
            
            # Format results
            formatted_results = []
            if results['ids']:
                for i in range(len(results['ids'][0])):
                    result_item = {
                        "id": results['ids'][0][i],
                        "content": results['documents'][0][i] if 'documents' in results else None,
                        "distance": results['distances'][0][i] if 'distances' in results else None
                    }
                    result_item["similarity"] = self._distance_to_similarity(
                        result_item["distance"]
                    )
                    
                    # Aggiungi metadata solo se richiesto e disponibile
                    if include_metadata and 'metadatas' in results:
                        result_item["metadata"] = results['metadatas'][0][i]
                    
                    if result_item["similarity"] >= min_similarity:
                        formatted_results.append(result_item)
            
            logger.info(f"Query returned {len(formatted_results)} results")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error during query: {e}")
            return []

    @staticmethod
    def _distance_to_similarity(distance: Optional[float]) -> float:
        """Convert Chroma cosine distance to a stable 0..1 similarity score."""
        if distance is None:
            return 0.0
        try:
            return max(0.0, min(1.0, 1.0 - float(distance)))
        except (TypeError, ValueError):
            return 0.0

    def _get_reranker(self):
        """Lazy-load the cross-encoder once per service instance."""
        if self._reranker is None:
            from sentence_transformers import CrossEncoder

            logger.info(f"Loading reranker model: {self.reranker_model_name}")
            self._reranker = CrossEncoder(self.reranker_model_name)
        return self._reranker

    def query_with_reranking(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict] = None,
        include_metadata: bool = True,
        rerank_factor: int = 3,
        min_similarity: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Ricerca semantica con cross-encoder re-ranking.

        Strategia: over-fetch n_results*rerank_factor candidati da ChromaDB,
        ri-ordina con cross-encoder ms-marco-MiniLM-L-6-v2, ritorna top n_results.
        Significativamente più preciso su query brevi o ambigue rispetto al solo coseno.

        Args:
            query_text: Testo query
            n_results: Numero risultati finali
            where: Filtro metadata ChromaDB
            include_metadata: Se includere metadati
            rerank_factor: Moltiplicatore candidati iniziali (default 3x)
            min_similarity: Soglia minima cosine similarity normalizzata [0, 1]
        """
        try:
            reranker = self._get_reranker()
        except Exception as e:
            logger.warning(f"CrossEncoder non disponibile ({e}), fallback a query standard")
            return self.query(
                query_text,
                n_results=n_results,
                where=where,
                include_metadata=include_metadata,
                min_similarity=min_similarity
            )

        # Over-fetch candidati
        candidates_n = min(n_results * rerank_factor, 100)
        candidates = self.query(
            query_text,
            n_results=candidates_n,
            where=where,
            include_metadata=include_metadata,
            min_similarity=min_similarity
        )

        if not candidates:
            return []

        try:
            scored_candidates = [c for c in candidates if c.get("content")]
            pairs = [(query_text, c["content"]) for c in scored_candidates]
            scores = reranker.predict(pairs)

            for candidate, score in zip(scored_candidates, scores):
                candidate["rerank_score"] = float(score)

            candidates.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
            logger.info(f"Re-ranking: {len(candidates)} candidati → top {n_results}")
            return candidates[:n_results]

        except Exception as e:
            logger.warning(f"Re-ranking fallito ({e}), fallback a risultati coseno")
            return candidates[:n_results]

    def update_chunk(
        self,
        chunk_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Aggiorna chunk esistente.
        
        Args:
            chunk_id: ID chunk da aggiornare
            content: Nuovo contenuto (None = non cambiare)
            metadata: Nuovi metadata (None = non cambiare)
            
        Returns:
            Dict con risultato operazione
            
        Note:
            Se cambi content, l'embedding viene rigenerato automaticamente
        """
        try:
            # Verifica che il chunk esista
            existing = self.get_chunk(chunk_id)
            if not existing:
                return {
                    "status": "error",
                    "message": f"Chunk {chunk_id} not found"
                }
            
            update_data = {"ids": [chunk_id]}
            
            # Aggiungi timestamp di aggiornamento
            new_metadata = existing['metadata'].copy()
            if metadata:
                new_metadata.update(metadata)
            new_metadata['updated_at'] = datetime.now().isoformat()
            
            if content is not None:
                update_data["documents"] = [content]
                
                # Rigenera embedding se custom embedder
                if self.embedder:
                    new_embedding = self.embedder.embed_single(content).tolist()
                    update_data["embeddings"] = [new_embedding]
            
            update_data["metadatas"] = [new_metadata]
            
            self.collection.update(**update_data)
            logger.info(f"Chunk {chunk_id} updated successfully")
            
            return {
                "status": "success",
                "chunk_id": chunk_id,
                "updated_fields": {
                    "content": content is not None,
                    "metadata": metadata is not None
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to update chunk {chunk_id}: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def delete_chunks(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Elimina chunks per ID o filtro metadata.
        
        Args:
            ids: Lista ID chunk da eliminare
            where: Filtro metadata per eliminazione batch
            
        Returns:
            Dict con risultato operazione
            
        Example:
            >>> # Elimina per ID
            >>> result = vector_store.delete_chunks(ids=["chunk_1", "chunk_2"])
            >>> 
            >>> # Elimina tutti chunk di un file
            >>> result = vector_store.delete_chunks(where={"source": "old_doc.pdf"})
        """
        try:
            # Conta chunk che verranno eliminati
            count_before = self.collection.count()
            
            self.collection.delete(ids=ids, where=where)
            
            count_after = self.collection.count()
            deleted_count = count_before - count_after
            
            if ids:
                logger.info(f"Deleted {deleted_count} chunks by ID")
                return {
                    "status": "success",
                    "deleted_count": deleted_count,
                    "deleted_by": "ids"
                }
            elif where:
                logger.info(f"Deleted {deleted_count} chunks matching filter: {where}")
                return {
                    "status": "success",
                    "deleted_count": deleted_count,
                    "deleted_by": "where",
                    "filter": where
                }
            else:
                # Se nessun parametro, non fare nulla
                return {
                    "status": "error",
                    "message": "Either 'ids' or 'where' must be specified"
                }
            
        except Exception as e:
            logger.error(f"Failed to delete chunks: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Ritorna statistiche collection per monitoring.
        
        Returns:
            dict con count, embedder_info, etc.
        """
        try:
            count = self.collection.count()
            
            # Ottieni metadata collection
            collection_metadata = self.collection.metadata or {}
            
            stats = {
                "collection_name": self.collection.name,
                "total_chunks": count,
                "embedder_type": "custom" if self.embedder else "chromadb_default",
                "metadata": collection_metadata,
                "timestamp": datetime.now().isoformat()
            }
            
            if self.embedder:
                stats["embedder_info"] = self.embedder.get_model_info()
            
            return {
                "status": "success",
                "stats": stats
            }
            
        except Exception as e:
            logger.error(f"Error getting collection stats: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def search_by_metadata(
        self,
        where: Dict[str, Any],
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Ricerca chunks per metadata senza semantic search.
        
        Args:
            where: Filtro metadata
            limit: Limite risultati
            
        Returns:
            Lista di chunks che corrispondono al filtro
        """
        try:
            # Usa query con testo vuoto per ottenere solo i risultati filtrati
            results = self.collection.get(
                where=where,
                limit=limit
            )
            
            formatted_results = []
            for i in range(len(results['ids'])):
                formatted_results.append({
                    "id": results['ids'][i],
                    "content": results['documents'][i],
                    "metadata": results['metadatas'][i]
                })
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error searching by metadata: {e}")
            return []
    
    def list_collections(self) -> List[str]:
        """
        Lista tutte le collezioni disponibili nel client ChromaDB.
        
        Returns:
            Lista di nomi delle collezioni
        """
        try:
            # ChromaDB client ha metodo list_collections() che restituisce oggetti Collection
            collections = self.client.list_collections()
            
            # Estrai solo i nomi
            collection_names = [col.name for col in collections]
            
            logger.info(f"Found {len(collection_names)} collections: {collection_names}")
            return collection_names
            
        except Exception as e:
            logger.error(f"Error listing collections: {e}")
            return []


# Convenience functions
def get_default_vector_store(
    collection_name: str = "document_chunks",
    db_path: str = "./data/chroma_db",
    embedder: Optional[SemanticEmbedder] = None
) -> VectorStoreService:
    """
    Factory function per vector store con configurazione ottimizzata (locale).
    
    Args:
        collection_name: Nome collection
        db_path: Path database locale
        embedder: Optional custom embedder (None = default)
        
    Returns:
        VectorStoreService configurato con embedder ottimizzato
    """
    if embedder is None:
        embedder = get_default_embedder()
    
    return VectorStoreService(
        collection_name=collection_name,
        db_path=db_path,
        embedder=embedder,
        use_custom_embedder=True
    )


def get_remote_vector_store(
    collection_name: str = "document_chunks",
    host: str = "localhost",
    port: int = 8000,
    embedder: Optional[SemanticEmbedder] = None
) -> VectorStoreService:
    """
    Factory function per vector store connesso a server ChromaDB remoto.
    
    Args:
        collection_name: Nome collection
        host: Host server ChromaDB
        port: Porta server ChromaDB
        embedder: Custom embedder (None = default)
        
    Returns:
        VectorStoreService configurato per server remoto
    """
    if embedder is None:
        embedder = get_default_embedder()
    
    return VectorStoreService(
        collection_name=collection_name,
        chroma_server_host=host,
        chroma_server_port=port,
        embedder=embedder,
        use_custom_embedder=True
    )
