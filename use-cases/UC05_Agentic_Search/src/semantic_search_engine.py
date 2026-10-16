"""
Semantic Search Engine - FIXED VERSION
"""
import time
import re
from typing import List, Dict, Optional, Tuple
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from .models import Book, QueryIntent, SearchResult
from .fuzzy_matcher import FuzzyMatcher

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMER_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMER_AVAILABLE = False


class SemanticSearchEngine:
    """Hybrid: semantic search con priorita corretta"""
    
    def __init__(self, use_semantic: bool = True):
        self.books: List[Book] = []
        self.fuzzy_matcher = FuzzyMatcher(threshold=60.0)
        self.use_semantic = use_semantic and SENTENCE_TRANSFORMER_AVAILABLE
        self.model = None
        self.embeddings = None
        
        if self.use_semantic:
            try:
                print("🧠 Loading Semantic Model...")
                print("   Model: sentence-transformers/all-MiniLM-L6-v2")
                print("   Embedding dimension: 384")
                self.model = SentenceTransformer('all-MiniLM-L6-v2')
                print("   ✅ Model loaded successfully")
            except Exception as e:
                print(f"   ⚠️  Semantic model failed to load: {e}")
                self.use_semantic = False
    
    def load_books(self, books_data: List[Dict]):
        self.books = [Book(**book) for book in books_data]
        
        if self.use_semantic:
            print(f"🔄 Encoding {len(self.books)} books...")
            texts = [f"{b.title} {' '.join(b.authors)} {b.description or ''}" for b in self.books]
            self.embeddings = self.model.encode(texts, show_progress_bar=False)
            print(f"   ✅ {len(self.books)} embeddings generated")
    
    def search(self, query: str, intent: QueryIntent, entities: Dict[str, str], limit: int = 10) -> SearchResult:
        start_time = time.time()
        
        if intent == QueryIntent.SEARCH_BY_AUTHOR:
            books, confidence = self._search_by_author(entities.get("author", query), limit)
        elif intent == QueryIntent.SEARCH_BY_TITLE:
            books, confidence = self._search_by_title(entities.get("title", query), limit)
        else:
            books, confidence = self._search_by_keyword(entities.get("keyword", query), limit)
        
        search_time = (time.time() - start_time) * 1000
        return SearchResult(books=books, query=query, intent=intent, total_results=len(books), confidence_score=confidence, search_time_ms=search_time)
    
    def _search_by_author(self, author_query: str, limit: int = 10) -> Tuple[List[Book], float]:
        """FIXED: Threshold abbassato per permettere typo + filtro gap score"""
        all_authors = []
        author_to_books = {}
        for book in self.books:
            for author in book.authors:
                if author not in author_to_books:
                    author_to_books[author] = []
                    all_authors.append(author)
                author_to_books[author].append(book)
        
        # Aumenta limit per catturare piu match
        matches = self.fuzzy_matcher.match(author_query, all_authors, limit=10)
        phonetic_matches = self.fuzzy_matcher.match_phonetic(author_query, all_authors, limit=10)
        
        all_matches = {}
        for match_text, score, idx in matches + phonetic_matches:
            original_author = all_authors[idx]
            all_matches[original_author] = max(all_matches.get(original_author, 0), score)
        
        # THRESHOLD RIDOTTO: 50.0 invece di 55.0 per permettere match su typo
        if not all_matches or max(all_matches.values()) < 50.0:
            return [], 0.0
        
        # NEW: Filtra autori con score troppo basso rispetto al migliore
        best_score = max(all_matches.values())
        min_acceptable_score = best_score - 20.0  # Max gap di 20 punti dal migliore
        
        filtered_matches = {
            author: score for author, score in all_matches.items()
            if score >= min_acceptable_score
        }
        
        result_books = []
        max_confidence = 0.0
        
        for author, score in sorted(filtered_matches.items(), key=lambda x: x[1], reverse=True):
            if author in author_to_books:
                for book in author_to_books[author]:
                    if book not in result_books:
                        result_books.append(book)
                        max_confidence = max(max_confidence, score)
                    if len(result_books) >= limit:
                        break
            if len(result_books) >= limit:
                break
        
        return result_books[:limit], max_confidence
    
    def _search_by_title(self, title_query: str, limit: int = 10) -> Tuple[List[Book], float]:
        """BOMB-PROOF: Substring + Fuzzy"""
        all_titles = [book.title for book in self.books]
        query_lower = title_query.lower()
        
        # 1. Substring matching
        substring_matches = []
        for idx, title in enumerate(all_titles):
            if query_lower in title.lower():
                score = 90.0
                substring_matches.append((title, score, idx))
        
        if substring_matches:
            substring_matches.sort(key=lambda x: x[1], reverse=True)
            book_scores = {idx: score for _, score, idx in substring_matches[:limit]}
        else:
            # 2. Fuzzy fallback
            matches = self.fuzzy_matcher.match(title_query, all_titles, limit=limit)
            book_scores = {}
            for match_text, score, idx in matches:
                book_scores[idx] = max(book_scores.get(idx, 0), score)
        
        sorted_indices = sorted(book_scores.keys(), key=lambda x: book_scores[x], reverse=True)
        result_books = [self.books[idx] for idx in sorted_indices[:limit]]
        max_confidence = max(book_scores.values()) if book_scores else 0.0
        
        if max_confidence < 55.0:
            return [], 0.0
        
        return result_books, max_confidence
    
    def _search_by_keyword(self, keyword: str, limit: int = 10) -> Tuple[List[Book], float]:
        """FIXED: Semantic search con priorita corretta"""
        if not keyword or not keyword.strip():
            return [], 0.0
        
        clean_kw = keyword.lower().strip()
        
        # 1. SEMANTIC FIRST per query concettuali (2+ parole)
        if self.use_semantic and self.embeddings is not None and len(clean_kw.split()) >= 2:
            query_embedding = self.model.encode([keyword])
            similarities = cosine_similarity(query_embedding, self.embeddings).flatten()
            top_indices = np.argsort(similarities)[-limit * 2:][::-1]  # Prendi piu candidati
            
            # Threshold ABBASSATO per semantic (era 0.2, ora 0.15)
            semantic_results = []
            for idx in top_indices:
                if similarities[idx] > 0.15:
                    book = self.books[idx]
                    score = similarities[idx] * 100
                    
                    # POST-FILTER: Dai BONUS a substring matches
                    text = f"{book.title} {book.description or ''}".lower()
                    if clean_kw in text:
                        score = min(score + 20, 100)  # Boost di 20 punti!
                    
                    semantic_results.append((book, score))
            
            if semantic_results:
                semantic_results.sort(key=lambda x: x[1], reverse=True)
                books = [book for book, _ in semantic_results[:limit]]
                max_conf = semantic_results[0][1]
                return books, max_conf
        
        # 2. Substring matching (fallback per query corte o semantic fallito)
        substring_matches = []
        for idx, book in enumerate(self.books):
            text = f"{book.title} {book.description or ''}".lower()
            if clean_kw in text:
                # Prioritize title matches
                score = 95.0 if clean_kw in book.title.lower() else 85.0
                substring_matches.append((book, score, idx))
        
        if substring_matches:
            substring_matches.sort(key=lambda x: x[1], reverse=True)
            return [m[0] for m in substring_matches[:limit]], substring_matches[0][1]
        
        # 3. Fallback finale: title fuzzy
        return self._search_by_title(keyword, limit)
    
    def get_book_by_id(self, book_id: str) -> Optional[Book]:
        for book in self.books:
            if book.id == book_id:
                return book
        return None
    
    def get_next_in_series(self, book: Book) -> Optional[Book]:
        numbers = re.findall(r'\d+', book.title)
        if not numbers:
            return None
        
        current_num = int(numbers[0])
        next_num = current_num + 1
        
        for other in self.books:
            if other.authors == book.authors and str(next_num) in other.title:
                return other
        return None
