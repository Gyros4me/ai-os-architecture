"""
Fuzzy matching and multilingual text processing utilities
"""
import re
import unicodedata
from typing import List, Tuple, Optional
from rapidfuzz import fuzz, process
from unidecode import unidecode
import langdetect


class TextNormalizer:
    """Normalize text for better matching across languages and transcription errors"""
    
    @staticmethod
    def normalize(text: str) -> str:
        """
        Comprehensive text normalization:
        - Lowercase
        - Remove accents/diacritics
        - Remove special characters
        - Collapse whitespace
        """
        if not text:
            return ""
        
        text = text.lower()
        text = unidecode(text)
        text = re.sub(r'[^a-z0-9\s]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    @staticmethod
    def phonetic_normalize(text: str) -> str:
        """
        Phonetic normalization for common transcription errors
        Handles Italian-specific phonetic patterns
        """
        text = TextNormalizer.normalize(text)
        replacements = {
            'ph': 'f', 'th': 't', 'gh': 'g', 'ck': 'k', 'ch': 'k',
            'qu': 'kw', 'x': 'ks', 'y': 'i', 'w': 'v', 'j': 'g', 'sch': 'sk',
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text


class FuzzyMatcher:
    """Fuzzy matching with multiple strategies for robust search"""
    
    def __init__(self, threshold: float = 70.0):
        self.threshold = threshold
        self.normalizer = TextNormalizer()
    
    def match(self, query: str, candidates: List[str], limit: int = 10) -> List[Tuple[str, float, int]]:
        """Fuzzy match query against candidates"""
        if not query or not candidates:
            return []
        
        normalized_query = self.normalizer.normalize(query)
        normalized_candidates = [self.normalizer.normalize(c) for c in candidates]
        
        results = process.extract(normalized_query, normalized_candidates, scorer=fuzz.WRatio, limit=limit, score_cutoff=self.threshold)
        return results
    
    def match_phonetic(self, query: str, candidates: List[str], limit: int = 10) -> List[Tuple[str, float, int]]:
        """Phonetic fuzzy matching for transcription errors"""
        if not query or not candidates:
            return []
        
        phonetic_query = self.normalizer.phonetic_normalize(query)
        phonetic_candidates = [self.normalizer.phonetic_normalize(c) for c in candidates]
        
        results = process.extract(phonetic_query, phonetic_candidates, scorer=fuzz.ratio, limit=limit, score_cutoff=self.threshold - 10)
        return results
    
    def best_match(self, query: str, candidates: List[str], original_candidates: Optional[List[str]] = None) -> Tuple[Optional[str], float]:
        """Get single best match combining multiple strategies"""
        if not query or not candidates:
            return None, 0.0
        
        normalized_query = self.normalizer.normalize(query)
        normalized_candidates = [self.normalizer.normalize(c) for c in candidates]
        
        if normalized_query in normalized_candidates:
            idx = normalized_candidates.index(normalized_query)
            original = original_candidates[idx] if original_candidates else candidates[idx]
            return original, 100.0
        
        fuzzy_results = self.match(query, candidates, limit=1)
        phonetic_results = self.match_phonetic(query, candidates, limit=1)
        
        best_score = 0.0
        best_idx = 0
        
        if fuzzy_results and fuzzy_results[0][1] > best_score:
            best_score = fuzzy_results[0][1]
            best_idx = fuzzy_results[0][2]
        
        if phonetic_results and phonetic_results[0][1] > best_score:
            best_score = phonetic_results[0][1]
            best_idx = phonetic_results[0][2]
        
        if best_score > 0:
            original = original_candidates[best_idx] if original_candidates else candidates[best_idx]
            return original, best_score
        
        return None, 0.0


class MultilingualMatcher:
    """Handle multilingual book title and author matching"""
    
    def __init__(self):
        self.normalizer = TextNormalizer()
    
    def detect_language(self, text: str) -> str:
        """Detect language of text"""
        try:
            return langdetect.detect(text)
        except:
            return "unknown"
    
    def create_search_variants(self, text: str) -> List[str]:
        """Create multiple search variants for cross-lingual matching"""
        variants = [text, text.lower(), self.normalizer.normalize(text), self.normalizer.phonetic_normalize(text)]
        
        seen = set()
        unique_variants = []
        for v in variants:
            if v and v not in seen:
                seen.add(v)
                unique_variants.append(v)
        
        return unique_variants