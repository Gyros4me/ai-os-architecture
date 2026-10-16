"""
Context manager for conversation tracking - FINAL FIX
"""
from typing import Dict, Optional
from datetime import datetime, timedelta
import re
from .models import ConversationContext, QueryIntent

# SOLO gli autori che vuoi supportare come parziali
PARTIAL_AUTHOR_DB = {
    "eco": "Umberto Eco",
    "tolkien": "J.R.R. Tolkien",
}

# Lista di aggettivi/concetti che indicano KEYWORD search
CONCEPTUAL_KEYWORDS = {
    'triste', 'tristi', 'tristezza', 'felice', 'felici', 'felicità',
    'azione', 'avventura', 'romantico', 'romantica', 'amore', 
    'paura', 'terrore', 'mistero', 'fantasy', 'storico', 'storia',
    'futuro', 'passato', 'guerra', 'pace', 'viaggio', 'scoperta',
    'magia', 'magico', 'magica', 'epico', 'epica', 'eroico', 'eroica',
    'drammatico', 'drammatica', 'comico', 'comica', 'divertente',
    'sereno', 'serena', 'cupo', 'cupa', 'oscuro', 'oscura',
    'allegro', 'allegra', 'malinconico', 'malinconica', 'melanconico',
    'tragico', 'tragica', 'poetico', 'poetica', 'filosofico', 'filosofica',
    'scientifico', 'scientifica', 'tecnologico', 'tecnologica',
    'giovane', 'giovani', 'vecchio', 'vecchi', 'moderno', 'moderna',
    'antico', 'antica', 'contemporaneo', 'contemporanea'
}

class ContextManager:
    """Manage conversation context for multi-turn interactions"""
    
    def __init__(self, ttl_minutes: int = 30):
        self.contexts: Dict[str, ConversationContext] = {}
        self.ttl = timedelta(minutes=ttl_minutes)
    
    def get_or_create_context(self, session_id: str, user_id: str) -> ConversationContext:
        if session_id in self.contexts:
            context = self.contexts[session_id]
            if datetime.now() - context.updated_at > self.ttl:
                context = ConversationContext(session_id=session_id, user_id=user_id)
                self.contexts[session_id] = context
            return context
        else:
            context = ConversationContext(session_id=session_id, user_id=user_id)
            self.contexts[session_id] = context
            return context
    
    def update_context(self, session_id: str, query: str, intent: QueryIntent, results: list, metadata: dict):
        if session_id not in self.contexts:
            return
        
        context = self.contexts[session_id]
        context.last_query = query
        context.last_intent = intent
        context.last_results = results
        context.metadata = metadata
        context.updated_at = datetime.now()
        
        context.messages.append({
            "query": query,
            "intent": intent.value,
            "timestamp": context.updated_at.isoformat()
        })

class IntentDetector:
    """Detect user intent - FINAL FIXED VERSION"""
    
    # STOPWORDS ridotte
    AGGRESSIVE_STOPWORDS = {'il', 'la', 'lo', 'un', 'una', 'e', 'di', 'a', 'da', 'in', 'con', 'cerca', 'cerco', 'libro', 'libri', 'del', 'al', 'ai', 'gli', 'le', 'della', 'degli', 'delle', 'per', 'su', 'tra', 'fra', 'mi', 'riferivo', 'intendevo', 'parlavo'}
    
    NEXT_KEYWORDS = ["secondo", "terzo", "quarto", "prossimo", "successivo", "altro", "altri"]
    CLARIFY_KEYWORDS = ["mi riferivo", "intendevo", "parlavo di", "quello", "non quello"]
    
    def detect(self, query: str, context: Optional[ConversationContext] = None) -> QueryIntent:
        query_lower = query.lower().strip()
        
        # Multi-turn PRIMA
        if context and context.last_results:
            if any(kw in query_lower for kw in self.NEXT_KEYWORDS):
                return QueryIntent.FOLLOWUP_NEXT
            if any(kw in query_lower for kw in self.CLARIFY_KEYWORDS):
                return QueryIntent.FOLLOWUP_CLARIFICATION
        
        # Author detection - PRIORITA MASSIMA
        if "libri di " in query_lower or "libro di " in query_lower:
            return QueryIntent.SEARCH_BY_AUTHOR
        
        # Parse words
        words = query_lower.split()
        
        # FIX: "libro eco" -> author se eco in db
        if len(words) == 2 and words[0] == "libro":
            if words[1] in PARTIAL_AUTHOR_DB:
                return QueryIntent.SEARCH_BY_AUTHOR
        
        # NUOVO: Controlla se contiene aggettivi/concetti
        # Es: "libro triste", "libri d'azione" -> KEYWORD
        for word in words:
            # Pulisci apostrofi
            clean_word = word.replace("'", "").replace("d", "").strip()
            if clean_word in CONCEPTUAL_KEYWORDS:
                return QueryIntent.SEARCH_BY_KEYWORD
        
        # NUOVO: Query singola lunga (>3 chars) -> potrebbe essere autore
        # Esempi: "murakami", "tolkien", "king", "muradami" (typo)
        if len(words) == 1 and len(words[0]) > 3:
            # Controlla se NON è un concetto
            if words[0] not in CONCEPTUAL_KEYWORDS:
                return QueryIntent.SEARCH_BY_AUTHOR
        
        # Default: keyword per query lunghe (3+), title per corte (1-2)
        if len(words) >= 3:
            return QueryIntent.SEARCH_BY_KEYWORD
        
        # Query corte (1-2 parole) senza concetti -> title
        return QueryIntent.SEARCH_BY_TITLE
    
    def extract_entities(self, query: str, intent: QueryIntent) -> Dict[str, str]:
        entities = {}
        query_lower = query.lower().strip()
        
        # Author extraction
        if intent == QueryIntent.SEARCH_BY_AUTHOR:
            # Pattern "libri di X"
            match = re.search(r"(?:libro|libri)\s+di\s+(.+)", query, re.IGNORECASE)
            if match:
                author = match.group(1).strip()
                # FIX: Se partial, espandi
                if author.lower() in PARTIAL_AUTHOR_DB:
                    entities["author"] = PARTIAL_AUTHOR_DB[author.lower()]
                else:
                    entities["author"] = author
                return entities
            
            # Pattern "libro X" (ultima parola)
            words = [w for w in query.split() if w.lower() not in self.AGGRESSIVE_STOPWORDS]
            if words:
                last_word = words[-1].lower()
                if last_word in PARTIAL_AUTHOR_DB:
                    entities["author"] = PARTIAL_AUTHOR_DB[last_word]
                    return entities
                # NUOVO: Se query singola, usa direttamente
                if len(words) == 1:
                    entities["author"] = words[0]
                    return entities
        
        # Title/keyword extraction
        if intent in [QueryIntent.SEARCH_BY_TITLE, QueryIntent.SEARCH_BY_KEYWORD, QueryIntent.FOLLOWUP_CLARIFICATION]:
            # Remove clarification phrases
            clean_query = query_lower
            for kw in self.CLARIFY_KEYWORDS:
                clean_query = clean_query.replace(kw, "")
            
            words = [w for w in clean_query.split() if w.lower() not in self.AGGRESSIVE_STOPWORDS]
            if words:
                key = "keyword"
                if intent == QueryIntent.SEARCH_BY_TITLE: key = "title"
                entities[key] = " ".join(words)
        
        return entities
    
    def _normalize_author(self, name: str) -> str:
        name = name.lower().strip()
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', ' ', name)
        return name
