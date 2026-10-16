# src/services/dlq.py
"""
Dead Letter Queue - Versione Persistente con SQLite
====================================================
Versione completa con storage persistente per production.
"""
import sqlite3
import json
from enum import Enum
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FailureReason(str, Enum):
    """Categorie di errori"""
    PARSING_ERROR = "parsing_error"
    ENCODING_ERROR = "encoding_error"
    VECTOR_STORE_ERROR = "vector_store_error"
    TIMEOUT = "timeout"
    VALIDATION_ERROR = "validation_error"
    UNKNOWN = "unknown"


class DeadLetterQueue:
    """
    DLQ con storage persistente SQLite.
    Supporta tutte le operazioni CRUD per chunk/file falliti.
    """
    
    def __init__(self, db_path: str = "./data/dlq.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
        logger.info(f"DLQ initialized (persistent mode) - DB: {self.db_path}")
    
    def _init_database(self):
        """Inizializza schema database SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabella failed_chunks
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS failed_chunks (
            id TEXT PRIMARY KEY,
            chunk_id TEXT NOT NULL,
            content TEXT NOT NULL,
            error TEXT NOT NULL,
            reason TEXT NOT NULL,
            metadata TEXT,
            retry_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_retry_at TIMESTAMP,
            source TEXT
        )
        ''')
        
        # Tabella failed_files
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS failed_files (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            error TEXT NOT NULL,
            reason TEXT NOT NULL,
            file_size_bytes INTEGER,
            metadata TEXT,
            failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT
        )
        ''')
        
        # Indici per performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chunks_status ON failed_chunks(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chunks_reason ON failed_chunks(reason)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chunks_failed_at ON failed_chunks(failed_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_failed_at ON failed_files(failed_at)')
        
        conn.commit()
        conn.close()
    
    def add_failed_chunk(
        self,
        chunk_id: str,
        content: str,
        error: str,
        reason: FailureReason = FailureReason.UNKNOWN,
        metadata: Optional[Dict] = None,
        retry_count: int = 0,
        source: Optional[str] = None
    ):
        """Aggiunge chunk fallito al DLQ"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT INTO failed_chunks 
            (id, chunk_id, content, error, reason, metadata, retry_count, status, failed_at, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                f"chunk_{datetime.utcnow().timestamp()}_{chunk_id}",
                chunk_id,
                content[:5000],  # Limita lunghezza
                str(error)[:1000],
                reason.value,
                json.dumps(metadata) if metadata else None,
                retry_count,
                'pending',
                datetime.utcnow().isoformat(),
                source
            ))
            
            conn.commit()
            conn.close()
            
            logger.warning(f"DLQ: Failed chunk added - {chunk_id} ({reason.value})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add chunk to DLQ: {e}")
            return False
    
    def add_failed_file(
        self,
        filename: str,
        error: str,
        reason: FailureReason = FailureReason.UNKNOWN,
        file_size_bytes: int = 0,
        metadata: Optional[Dict] = None,
        source: Optional[str] = None
    ):
        """Aggiunge file fallito al DLQ"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT INTO failed_files 
            (id, filename, error, reason, file_size_bytes, metadata, failed_at, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                f"file_{datetime.utcnow().timestamp()}_{filename}",
                filename,
                str(error)[:1000],
                reason.value,
                file_size_bytes,
                json.dumps(metadata) if metadata else None,
                datetime.utcnow().isoformat(),
                source
            ))
            
            conn.commit()
            conn.close()
            
            logger.error(f"DLQ: Failed file added - {filename} ({reason.value})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add file to DLQ: {e}")
            return False
    
    def get_failed_chunks(
        self, 
        limit: int = 100,
        offset: int = 0,
        reason: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Recupera chunk falliti con filtri"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT * FROM failed_chunks WHERE 1=1"
            params = []
            
            if reason:
                query += " AND reason = ?"
                params.append(reason)
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            query += " ORDER BY failed_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            chunks = []
            for row in rows:
                chunk = dict(row)
                # Parsa metadata JSON
                if chunk.get('metadata'):
                    try:
                        chunk['metadata'] = json.loads(chunk['metadata'])
                    except:
                        chunk['metadata'] = {}
                chunks.append(chunk)
            
            conn.close()
            return chunks
            
        except Exception as e:
            logger.error(f"Failed to get failed chunks: {e}")
            return []
    
    def get_failed_files(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Recupera file falliti"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT * FROM failed_files 
            ORDER BY failed_at DESC 
            LIMIT ? OFFSET ?
            ''', (limit, offset))
            
            rows = cursor.fetchall()
            files = []
            for row in rows:
                file = dict(row)
                if file.get('metadata'):
                    try:
                        file['metadata'] = json.loads(file['metadata'])
                    except:
                        file['metadata'] = {}
                files.append(file)
            
            conn.close()
            return files
            
        except Exception as e:
            logger.error(f"Failed to get failed files: {e}")
            return []
    
    def get_failed_chunk(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Recupera un singolo chunk fallito per ID."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM failed_chunks WHERE id = ? OR chunk_id = ?', 
                         (chunk_id, chunk_id))
            row = cursor.fetchone()
            
            if row:
                chunk = dict(row)
                if chunk.get('metadata'):
                    try:
                        chunk['metadata'] = json.loads(chunk['metadata'])
                    except:
                        chunk['metadata'] = {}
                return chunk
            return None
        except Exception as e:
            logger.error(f"Error getting failed chunk {chunk_id}: {e}")
            return None
        finally:
            conn.close()
    
    def retry_chunk(self, chunk_id: str) -> bool:
        """Tenta di ritentare un chunk fallito"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Recupera il chunk
            cursor.execute('SELECT * FROM failed_chunks WHERE id = ? OR chunk_id = ?', (chunk_id, chunk_id))
            chunk = cursor.fetchone()
            
            if not chunk:
                return False
            
            # Incrementa retry count e aggiorna status
            cursor.execute('''
            UPDATE failed_chunks 
            SET retry_count = retry_count + 1, 
                status = 'retrying',
                last_retry_at = ?
            WHERE id = ? OR chunk_id = ?
            ''', (datetime.utcnow().isoformat(), chunk_id, chunk_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"DLQ: Retry initiated for chunk {chunk_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to retry chunk {chunk_id}: {e}")
            return False
    
    def mark_for_retry(self, chunk_id: str) -> bool:
        """Marca un chunk per retry (alias di retry_chunk)."""
        return self.retry_chunk(chunk_id)
    
    def remove_failed_chunk(self, chunk_id: str) -> bool:
        """Rimuovi un chunk dal DLQ (dopo successo)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM failed_chunks WHERE id = ? OR chunk_id = ?', 
                         (chunk_id, chunk_id))
            deleted = cursor.rowcount > 0
            
            conn.commit()
            conn.close()
            
            logger.info(f"Removed chunk {chunk_id} from DLQ")
            return deleted
        except Exception as e:
            logger.error(f"Error removing chunk {chunk_id}: {e}")
            return False
    
    def clear_permanent_failures(self, max_retries: int = 3) -> Dict[str, Any]:
        """Cancella fallimenti permanenti (retry_count > max_retries)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Conta prima
            cursor.execute('SELECT COUNT(*) FROM failed_chunks WHERE retry_count > ?', (max_retries,))
            count_before = cursor.fetchone()[0]
            
            # Cancella
            cursor.execute('DELETE FROM failed_chunks WHERE retry_count > ?', (max_retries,))
            deleted_count = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            logger.info(f"DLQ: Cleared {deleted_count} permanent failures")
            
            return {
                "deleted_count": deleted_count,
                "max_retries": max_retries,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to clear permanent failures: {e}")
            return {"deleted_count": 0, "error": str(e)}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Statistiche complete del DLQ"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Statistiche chunks
            cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'retrying' THEN 1 ELSE 0 END) as retrying,
                SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) as resolved,
                AVG(retry_count) as avg_retries
            FROM failed_chunks
            ''')
            chunk_stats = cursor.fetchone()
            
            # Statistiche per reason
            cursor.execute('''
            SELECT reason, COUNT(*) as count 
            FROM failed_chunks 
            GROUP BY reason
            ''')
            reasons = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Statistiche files
            cursor.execute('SELECT COUNT(*) FROM failed_files')
            file_count = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                "failed_chunks": {
                    "total": chunk_stats[0] if chunk_stats else 0,
                    "pending": chunk_stats[1] if chunk_stats else 0,
                    "retrying": chunk_stats[2] if chunk_stats else 0,
                    "resolved": chunk_stats[3] if chunk_stats else 0,
                    "avg_retries": round(chunk_stats[4] if chunk_stats and chunk_stats[4] else 0, 2)
                },
                "failed_files": {
                    "total": file_count
                },
                "reasons": reasons,
                "timestamp": datetime.utcnow().isoformat(),
                "mode": "persistent"
            }
            
        except Exception as e:
            logger.error(f"Failed to get DLQ statistics: {e}")
            return {
                "failed_chunks": {"total": 0},
                "failed_files": {"total": 0},
                "reasons": {},
                "error": str(e),
                "mode": "persistent"
            }
    
    def mark_chunk_resolved(self, chunk_id: str) -> bool:
        """Segna un chunk come risolto (cerca per id primario o per chunk_id)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
            UPDATE failed_chunks
            SET status = 'resolved'
            WHERE id = ? OR chunk_id = ?
            ''', (chunk_id, chunk_id))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            logger.error(f"Failed to mark chunk {chunk_id} as resolved: {e}")
            return False


# Singleton instance
_dlq_instance = None


def get_dlq(db_path: str = "./data/dlq.db") -> DeadLetterQueue:
    """Get global DLQ instance"""
    global _dlq_instance
    if _dlq_instance is None:
        _dlq_instance = DeadLetterQueue(db_path)
    return _dlq_instance