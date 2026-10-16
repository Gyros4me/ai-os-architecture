"""
Main conversational agent - FIXED: NO INTENT OVERRIDE
"""
import uuid
import re
from typing import Optional, List
from datetime import datetime

from .models import (
    SearchQuery, AgentResponse, SearchResult, QueryIntent, Book, ConversationContext
)
from .context_manager import ContextManager, IntentDetector

USING_SEMANTIC = False
try:
    from sentence_transformers import SentenceTransformer
    USING_SEMANTIC = True
except ImportError:
    pass


class BookSearchAgent:
    """Agent with BOMB-PROOF multi-turn"""
    
    def __init__(self, books_data: list, use_semantic: bool = True):
        if USING_SEMANTIC and use_semantic:
            from .semantic_search_engine import SemanticSearchEngine
            self.search_engine = SemanticSearchEngine(use_semantic=True)
            self.mode = "SEMANTIC"
        else:
            from .search_engine import BookSearchEngine
            self.search_engine = BookSearchEngine()
            self.mode = "FUZZY"
        
        self.search_engine.load_books(books_data)
        self.context_manager = ContextManager(ttl_minutes=30)
        self.intent_detector = IntentDetector()
    
    def process_query(self, search_query: SearchQuery) -> AgentResponse:
        query_raw = search_query.query
        query_stripped = re.sub(r'[^\w\s\àèéìòù]', ' ', query_raw.strip())
        query_stripped = re.sub(r'\s+', ' ', query_stripped).strip()
        
        if len(query_stripped) < 2:
            return self._create_error_response("Query troppo breve.", query_raw)
        
        session_id = search_query.session_id or str(uuid.uuid4())
        context = self.context_manager.get_or_create_context(session_id, search_query.user_id)
        intent = self.intent_detector.detect(query_stripped, context)
        
        if self._is_followup_intent(intent):
            return self._handle_followup(query_stripped, intent, context, session_id)
        
        entities = self.intent_detector.extract_entities(query_stripped, intent)
        
        # REMOVED: Vecchio codice che sovascriveva l'intent
        # L'intent detection è ora gestito correttamente da IntentDetector con CONCEPTUAL_KEYWORDS
        
        search_result = self.search_engine.search(query_stripped, intent, entities, limit=10)
        
        # FIX: Salva SEMPRE i risultati originali
        num_shown = min(5, len(search_result.books))
        
        self.context_manager.update_context(
            session_id=session_id,
            query=query_stripped,
            intent=intent,
            results=search_result.books,
            metadata={
                "entities": entities,
                "original_query": query_raw,
                "last_shown_index": num_shown - 1,
                "original_results": search_result.books
            }
        )
        
        message = self._generate_response_message(search_result, intent, entities)
        suggestions = self._generate_suggestions(search_result, intent)
        
        return AgentResponse(
            message=message,
            results=search_result,
            suggestions=suggestions,
            session_id=session_id
        )
    
    def _fuzzy_only_search(self, query: str, intent: QueryIntent, entities: dict, limit: int) -> SearchResult:
        proper_name = self._extract_proper_name(query)
        
        if not proper_name:
            return SearchResult(books=[], query=query, intent=intent, total_results=0, confidence_score=0.0, search_time_ms=0.0)
        
        fuzzy_books, fuzzy_conf = self.search_engine._search_by_title(proper_name, limit=limit)
        
        if fuzzy_conf > 75.0:
            intent = QueryIntent.SEARCH_BY_TITLE
        else:
            fuzzy_books, fuzzy_conf = self.search_engine._search_by_author(proper_name, limit=limit)
            if fuzzy_conf > 70.0:
                intent = QueryIntent.SEARCH_BY_AUTHOR
            else:
                return SearchResult(books=[], query=query, intent=intent, total_results=0, confidence_score=0.0, search_time_ms=0.0)
        
        return SearchResult(books=fuzzy_books, query=query, intent=intent, total_results=len(fuzzy_books), confidence_score=fuzzy_conf, search_time_ms=0.0)
    
    def _extract_proper_name(self, query: str) -> Optional[str]:
        stopwords = {
            "sto", "cercando", "cerca", "cerco", "libro", "libri", "titol", "titolo", 
            "autore", "con", "di", "del", "il", "la", "un", "una", "e", "a", "da", "in"
        }
        words = [w for w in query.lower().split() if w not in stopwords and len(w) > 2]
        return words[-1] if words else None
    
    def _apply_strict_filter(self, search_result: SearchResult, query: str, intent: QueryIntent) -> SearchResult:
        if intent == QueryIntent.SEARCH_BY_KEYWORD and search_result.books:
            words = [w for w in query.lower().split() if len(w) > 3]
            if not words:
                return search_result
            
            filtered = []
            for book in search_result.books:
                text = f"{book.title} {book.description or ''}".lower()
                if all(re.search(r'\b' + re.escape(w) + r'\b', text) for w in words):
                    filtered.append(book)
            
            if not filtered:
                return SearchResult(books=[], query=query, intent=intent, total_results=0, confidence_score=0.0, search_time_ms=search_result.search_time_ms)
            
            search_result.books = filtered
            search_result.total_results = len(filtered)
        
        return search_result
    
    def _is_followup_intent(self, intent: QueryIntent) -> bool:
        return intent in [
            QueryIntent.FOLLOWUP_NEXT,
            QueryIntent.FOLLOWUP_PREVIOUS,
            QueryIntent.FOLLOWUP_CLARIFICATION
        ]
    
    def _handle_followup(
        self,
        query: str,
        intent: QueryIntent,
        context: ConversationContext,
        session_id: str
    ) -> AgentResponse:
        """BOMB-PROOF: mai resettare i risultati"""
        # FIX: Usa SEMPRE i risultati originali salvati
        original_results = context.metadata.get("original_results", context.last_results)
        
        if not original_results:
            return self._create_error_response("Nessun contesto precedente.", query)
        
        if intent == QueryIntent.FOLLOWUP_NEXT:
            # FIX: Prova sempre la serie prima
            first_book = original_results[0]
            next_book = self.search_engine.get_next_in_series(first_book)
            
            if next_book:
                books = [next_book]
                message = f"Ecco il seguito della saga: '{next_book.title}'"
                confidence = 95.0
            else:
                # FIX: Determina posizione
                query_lower = query.lower()
                position = None
                
                if "secondo" in query_lower:
                    position = 1
                elif "terzo" in query_lower:
                    position = 2
                elif "quarto" in query_lower:
                    position = 3
                elif "quinto" in query_lower:
                    position = 4
                else:
                    position = context.metadata.get("last_shown_index", -1) + 1
                
                if position >= len(original_results):
                    return self._create_error_response(f"Non ci sono più risultati (solo {len(original_results)} disponibili).", query)
                
                # FIX: Restituisci sempre dalla lista originale
                books = [original_results[position]]
                message = f"Ecco il risultato #{position + 1}: '{books[0].title}'"
                confidence = 90.0
                
                # Aggiorna last_shown_index
                context.metadata["last_shown_index"] = position
        
        elif intent == QueryIntent.FOLLOWUP_CLARIFICATION:
            # Prova a filtrare i risultati precedenti con la nuova keyword
            entities = self.intent_detector.extract_entities(query, intent)
            keyword = entities.get("keyword", "").lower()
            
            if keyword:
                filtered_books = []
                for book in original_results:
                    text = f"{book.title} {book.description or ''}".lower()
                    if keyword in text:
                        filtered_books.append(book)
                
                if filtered_books:
                    books = filtered_books
                    message = f"Ho filtrato i risultati per '{keyword}':"
                    confidence = 95.0
                else:
                    # Se il filtro fallisce, prova una nuova ricerca globale
                    search_result = self.search_engine.search(query, QueryIntent.SEARCH_BY_KEYWORD, entities, limit=10)
                    if search_result.books:
                        return AgentResponse(
                            message=f"Non ho trovato nulla tra i risultati precedenti, ma ecco cosa ho trovato per '{keyword}':",
                            results=search_result,
                            suggestions=self._generate_suggestions(search_result, QueryIntent.SEARCH_BY_KEYWORD),
                            session_id=session_id
                        )
                    return self._create_error_response(f"Non ho trovato libri relativi a '{keyword}'.", query)
            else:
                # Fallback: Mostra alternative
                start_idx = max(1, context.metadata.get("last_shown_index", 0))
                alternative_books = original_results[start_idx:start_idx + 5]
                if alternative_books:
                    books = alternative_books
                    message = f"Altri risultati ({start_idx + 1}-{start_idx + len(books)}):"
                    confidence = 85.0
                else:
                    return self._create_error_response("Nessuna alternativa disponibile.", query)
        
        else:  # FOLLOWUP_PREVIOUS
            books = original_results[:1]
            message = "Primo risultato della ricerca precedente:"
            confidence = 90.0
        
        search_result = SearchResult(books=books, query=query, intent=intent, total_results=len(books), confidence_score=confidence, search_time_ms=0.0)
        
        # FIX: NON aggiornare last_results, solo metadati
        context.last_query = query
        context.last_intent = intent
        context.updated_at = datetime.now()
        
        return AgentResponse(message=message, results=search_result, suggestions=self._generate_suggestions(search_result, intent), session_id=session_id)
    
    def _apply_strict_context_filter(self, books: List[Book], original_query: str) -> List[Book]:
        """Filtro contesto"""
        if not books or not original_query:
            return books
        
        stopwords = {
            'il', 'la', 'lo', 'un', 'una', 'e', 'di', 'a', 'da', 'in', 'con', 'su', 'per',
            'tra', 'fra', 'è', 'sono', 'cerca', 'cerco', 'libro', 'libri', 'del', 'della',
            'qual', 'quale', 'quel', 'quella'
        }
        query_words = set(w for w in original_query.lower().split() if w not in stopwords and len(w) > 2)
        
        if not query_words:
            return books
        
        filtered_books = []
        for book in books:
            text_to_check = f"{book.title} {book.description or ''}".lower()
            text_words = set(text_to_check.split())
            intersection = query_words.intersection(text_words)
            main_word = list(query_words)[0]
            overlap_ratio = len(intersection) / len(query_words) if query_words else 0
            
            if overlap_ratio >= 0.3 or main_word in text_words:
                filtered_books.append(book)
        
        return filtered_books if filtered_books else books[:1]
    
    def _generate_response_message(self, search_result: SearchResult, intent: QueryIntent, entities: dict) -> str:
        if search_result.total_results == 0:
            return "Mi dispiace, non ho trovato libri corrispondenti alla tua ricerca."
        
        # Determina quanti libri vengono effettivamente mostrati
        num_shown = min(5, search_result.total_results)
        shown_suffix = f" (mostro i primi {num_shown})" if search_result.total_results > 5 else ""
        
        if intent == QueryIntent.SEARCH_BY_AUTHOR:
            author = entities.get("author", "questo autore")
            return f"Ho trovato {search_result.total_results} libri di {author}{shown_suffix}:"
        elif intent == QueryIntent.SEARCH_BY_TITLE:
            title = entities.get("title", "questo titolo")
            return f"Ho trovato {search_result.total_results} libri con il titolo '{title}'{shown_suffix}:"
        elif intent == QueryIntent.FOLLOWUP_NEXT:
            return search_result.query
        else:
            keyword = entities.get("keyword", "la tua ricerca")
            return f"Ho trovato {search_result.total_results} libri per la ricerca '{keyword}'{shown_suffix}:"
    
    def _generate_suggestions(self, search_result: SearchResult, intent: QueryIntent) -> list:
        suggestions = []
        if search_result.total_results > 1:
            suggestions.append("Vuoi sapere di più su uno di questi libri?")
            suggestions.append("Prova: 'e il secondo?'")
        return suggestions[:2]
    
    def _create_error_response(self, message: str, original_query: str) -> AgentResponse:
        return AgentResponse(
            message=message,
            results=SearchResult(books=[], query=original_query, intent=QueryIntent.SEARCH_BY_KEYWORD, total_results=0, confidence_score=0.0, search_time_ms=0.0),
            suggestions=["Prova con: 'libri di [autore]'", "Oppure: 'libro [parola]'"],
            session_id=str(uuid.uuid4())
        )
    
    def get_statistics(self) -> dict:
        return {
            "total_books": len(self.search_engine.books),
            "active_sessions": len(self.context_manager.contexts),
            "mode": self.mode
        }
