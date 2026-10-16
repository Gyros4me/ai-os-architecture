from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from enum import Enum
from datetime import datetime

class QueryIntent(Enum):
    SEARCH_BY_AUTHOR = "search_by_author"
    SEARCH_BY_TITLE = "search_by_title"
    SEARCH_BY_KEYWORD = "search_by_keyword"
    FOLLOWUP_NEXT = "followup_next"
    FOLLOWUP_PREVIOUS = "followup_previous"
    FOLLOWUP_CLARIFICATION = "followup_clarification"

class Book(BaseModel):
    id: str
    title: str
    authors: List[str]
    isbn: Optional[str] = None
    language_code: Optional[str] = None
    num_pages: Optional[int] = None
    ratings_count: Optional[int] = 0
    average_rating: Optional[float] = 0.0
    publication_date: Optional[str] = None
    publisher: Optional[str] = None
    description: Optional[str] = None

class SearchQuery(BaseModel):
    query: str
    user_id: Optional[str] = "default_user"
    session_id: Optional[str] = None

class SearchResult(BaseModel):
    books: List[Book]
    query: str
    intent: QueryIntent
    total_results: int
    confidence_score: float
    search_time_ms: float

class AgentResponse(BaseModel):
    message: str
    results: SearchResult
    suggestions: List[str]
    session_id: str

class ConversationContext(BaseModel):
    session_id: str
    user_id: str
    last_query: Optional[str] = None
    last_intent: Optional[QueryIntent] = None
    last_results: List[Book] = []
    metadata: Dict = {}
    messages: List[Dict] = []
    updated_at: datetime = Field(default_factory=datetime.now)
