"""
Test suite for Agentic Search Agent
"""
import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.agent import BookSearchAgent
from src.models import SearchQuery, QueryIntent
from src.data_loader import generate_sample_books


@pytest.fixture
def agent():
    """Create agent with sample data"""
    books_data = generate_sample_books()
    return BookSearchAgent(books_data)


@pytest.fixture
def sample_books():
    """Get sample books"""
    return generate_sample_books()


class TestFuzzyMatching:
    """Test fuzzy matching capabilities"""
    
    def test_author_fuzzy_match(self, agent):
        """Test fuzzy matching for author names"""
        # Test "Muradami" -> "Murakami"
        query = SearchQuery(query="Cerco un libro di Muradami")
        response = agent.process_query(query)
        
        assert response.results.total_results > 0
        assert any("Murakami" in author for book in response.results.books for author in book.authors)
    
    def test_title_fuzzy_match(self, agent):
        """Test fuzzy matching for titles"""
        query = SearchQuery(query="Libro con parola sole")
        response = agent.process_query(query)
        
        assert response.results.total_results > 0
    
    def test_phonetic_matching(self, agent):
        """Test phonetic normalization"""
        query = SearchQuery(query="Cerco libri di Rouling")  # Rowling
        response = agent.process_query(query)
        
        # Should still find J.K. Rowling books
        assert response.results.total_results > 0


class TestIntentDetection:
    """Test intent detection"""
    
    def test_author_intent(self, agent):
        """Test author search intent"""
        query = SearchQuery(query="Cerco un libro di J. K. Rowling")
        response = agent.process_query(query)
        
        assert response.results.intent == QueryIntent.SEARCH_BY_AUTHOR
        assert response.results.total_results > 0
    
    def test_title_intent(self, agent):
        """Test title search intent"""
        query = SearchQuery(query="Come si chiama quel libro intitolato Harry Potter")
        response = agent.process_query(query)
        
        assert response.results.intent == QueryIntent.SEARCH_BY_TITLE
    
    def test_keyword_intent(self, agent):
        """Test keyword search intent"""
        query = SearchQuery(query="Libro con la parola sole")
        response = agent.process_query(query)
        
        assert response.results.intent == QueryIntent.SEARCH_BY_KEYWORD


class TestContextTracking:
    """Test conversation context tracking"""
    
    def test_followup_query(self, agent):
        """Test follow-up queries maintain context"""
        # First query
        query1 = SearchQuery(query="Cerco libri di Tolkien")
        response1 = agent.process_query(query1)
        session_id = response1.session_id
        
        assert response1.results.total_results > 0
        
        # Follow-up query
        query2 = SearchQuery(
            query="E il secondo volume?",
            session_id=session_id
        )
        response2 = agent.process_query(query2)
        
        assert response2.results.intent == QueryIntent.FOLLOWUP_NEXT
    
    def test_session_isolation(self, agent):
        """Test that different sessions are isolated"""
        query1 = SearchQuery(query="Cerco libri di Rowling")
        response1 = agent.process_query(query1)
        
        # New session
        query2 = SearchQuery(query="E il secondo?")
        response2 = agent.process_query(query2)
        
        # Should have different session IDs
        assert response1.session_id != response2.session_id


class TestMultilingualSupport:
    """Test multilingual support"""
    
    def test_italian_query(self, agent):
        """Test Italian query"""
        query = SearchQuery(query="Cerco un libro di Umberto Eco")
        response = agent.process_query(query)
        
        assert response.results.total_results > 0
    
    def test_mixed_language(self, agent):
        """Test query in Italian for English titled book"""
        query = SearchQuery(query="Libro Norwegian Wood")
        response = agent.process_query(query)
        
        assert response.results.total_results > 0


class TestPerformance:
    """Test performance requirements"""
    
    def test_response_time(self, agent):
        """Test that response time is under 3 seconds"""
        query = SearchQuery(query="Cerco un libro di Murakami")
        response = agent.process_query(query)
        
        # Response time should be under 3000ms
        assert response.results.search_time_ms < 3000
    
    def test_bulk_queries(self, agent):
        """Test handling multiple queries"""
        queries = [
            "Cerco libri di Rowling",
            "Libro con parola sole",
            "Autore Murakami",
            "E il secondo volume?",
        ]
        
        session_id = None
        for q in queries:
            query = SearchQuery(query=q, session_id=session_id)
            response = agent.process_query(query)
            session_id = response.session_id
            
            assert response.results.search_time_ms < 3000


def test_agent_initialization(sample_books):
    """Test agent initialization"""
    agent = BookSearchAgent(sample_books)
    stats = agent.get_statistics()
    
    assert stats["total_books"] == len(sample_books)
    assert stats["active_sessions"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
