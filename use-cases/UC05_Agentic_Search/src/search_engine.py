"""
Catalog search engine - FIXED VERSION (fuzzy-only)
"""
import time
import re
from typing import List, Dict, Optional, Tuple
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd

from .models import Book, QueryIntent, SearchResult
from .fuzzy_matcher import FuzzyMatcher, TextNormalizer, MultilingualMatcher


class BookSearchEngine:
    """
    Hybrid search engine - FIXED VERSION
    """
    
    # THRESHOLD ORIGINALI che funzionavano
    FUZZY_MATCH_THRESHOLD = 60.0
    TFIDF_MIN_CONFIDENCE = 20.0
    FUZZY_MIN_CONFIDENCE = 50.0  # RIDOTTO da 55.0 a 50.0
    
    def __init__(self):
        self.books: List[Book] = []
        self.books_df: Optional[pd.DataFrame] = None
        self.tfidf_vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        self.fuzzy_matcher = FuzzyMatcher(threshold=self.FUZZY_MATCH_THRESHOLD)
        self.multilingual_matcher = MultilingualMatcher()
        self.normalizer = TextNormalizer()
        
    def load_books(self, books_data: List[Dict]):
        self.books = [Book(**book) for book in books_data]
        self.books_df = pd.DataFrame([book.model_dump() for book in self.books])
        self._build_search_index()
    
    def _build_search_index(self):
        if len(self.books) == 0:
            return
        
        search_texts = []
        for book in self.books:
            text_parts = [book.title, " ".join(book.authors), book.description or ""]
            search_texts.append(" ".join(text_parts))
        
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=5000, stop_words=None, ngram_range=(1, 2), min_df=1, token_pattern=r"(?u)\b\w+\b"
        )
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(search_texts)
    
    def search(self, query: str, intent: QueryIntent, entities: Dict[str, str], limit: int = 10) -> SearchResult:
        start_time = time.time()
        
        if intent == QueryIntent.SEARCH_BY_AUTHOR:
            books, confidence = self._search_by_author(entities.get("author", query), limit)
        elif intent == QueryIntent.SEARCH_BY_TITLE:
            books, confidence = self._search_by_title(entities.get("title", query), limit)
        else:  # Keyword
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
        
        # Fuzzy match su tutti gli autori (aumentato limit)
        matches = self.fuzzy_matcher.match(author_query, all_authors, limit=10)
        phonetic_matches = self.fuzzy_matcher.match_phonetic(author_query, all_authors, limit=10)
        
        all_matches = {}
        for match_text, score, idx in matches + phonetic_matches:
            original_author = all_authors[idx]
            all_matches[original_author] = max(all_matches.get(original_author, 0), score)
        
        # THRESHOLD RIDOTTO: 50.0 invece di 55.0
        if not all_matches or max(all_matches.values()) < self.FUZZY_MIN_CONFIDENCE:
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
        """BOMBA-PROOF: Substring + Fuzzy, threshold 50"""
        all_titles = [book.title for book in self.books]
        query_lower = title_query.lower()
        
        # 1. Substring matching
        substring_matches = []
        for idx, title in enumerate(all_titles):
            if query_lower in title.lower():
                score = 90.0  # Alto score per substring
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
        
        # Threshold piu basso per permettere match
        if max_confidence < self.FUZZY_MIN_CONFIDENCE:
            return [], 0.0
        
        return result_books, max_confidence
    
    def _search_by_keyword(self, keyword: str, limit: int = 10) -> Tuple[List[Book], float]:
        """Hybrid: Substring + TF-IDF"""
        if not keyword or not keyword.strip():
            return [], 0.0
        
        # Solo stopwords italiane
        stopwords = {'il', 'la', 'lo', 'un', 'una', 'e', 'di', 'a', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra', 'è', 'sono', 'cerca', 'cerco', 'libro', 'libri', 'del', 'della'}
        cleaned_keyword = " ".join([w for w in keyword.lower().split() if w not in stopwords])
        
        if not cleaned_keyword.strip():
            cleaned_keyword = keyword
        
        # 1. Substring matching in title and description
        substring_matches = []
        for idx, book in enumerate(self.books):
            text = f"{book.title} {book.description or ''}".lower()
            if cleaned_keyword in text:
                substring_matches.append((book, 95.0, idx))
        
        if substring_matches:
            return [m[0] for m in substring_matches[:limit]], 95.0
        
        # 2. TF-IDF fallback
        if self.tfidf_matrix is not None:
            try:
                query_vec = self.tfidf_vectorizer.transform([cleaned_keyword])
                similarities = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
                top_indices = np.argsort(similarities)[-limit:][::-1]
                
                filtered_indices = [idx for idx in top_indices if similarities[idx] >= 0.1]
                
                if filtered_indices:
                    result_books = [self.books[idx] for idx in filtered_indices[:limit]]
                    max_confidence = float(similarities[filtered_indices[0]] * 100)
                    return result_books, max_confidence
            except Exception:
                pass
        
        return self._search_by_title(cleaned_keyword, limit)
    
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
