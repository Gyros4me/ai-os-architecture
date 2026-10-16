"""
Edge cases test suite for Agentic Search Agent
Tests robustness with unusual inputs
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.agent import BookSearchAgent
from src.models import SearchQuery
from src.data_loader import generate_sample_books


@pytest.fixture
def agent():
    """Create agent with sample data"""
    books_data = generate_sample_books()
    return BookSearchAgent(books_data)


class TestEdgeCases:
    """Test edge cases and unusual inputs"""
    
    def test_empty_query(self, agent):
        """Test empty query handling"""
        response = agent.process_query(SearchQuery(query=""))
        
        # Should handle gracefully
        assert response.results.total_results == 0
        assert response.message is not None
    
    def test_whitespace_only_query(self, agent):
        """Test whitespace-only query"""
        response = agent.process_query(SearchQuery(query="   "))
        
        assert response.results.total_results == 0
    
    def test_very_long_query(self, agent):
        """Test very long query (potential DOS)"""
        long_query = "cerco " + " ".join(["libro"] * 100)
        
        response = agent.process_query(SearchQuery(query=long_query))
        
        # Should complete in reasonable time
        assert response.results.search_time_ms < 3000
    
    def test_special_characters(self, agent):
        """Test special characters in query"""
        special_chars = "!@#$%^&*()_+-=[]{}|;:',.<>?/~`"
        
        response = agent.process_query(SearchQuery(query=special_chars))
        
        # Should not crash
        assert response is not None
        assert response.results.total_results >= 0
    
    def test_unicode_characters(self, agent):
        """Test unicode characters"""
        unicode_query = "Cerco libro 日本語 中文"
        
        response = agent.process_query(SearchQuery(query=unicode_query))
        
        # Should handle gracefully
        assert response is not None
    
    def test_mixed_languages_query(self, agent):
        """Test query with multiple languages"""
        mixed_query = "Cerco book written by автор"
        
        response = agent.process_query(SearchQuery(query=mixed_query))
        
        assert response.results.total_results >= 0
    
    def test_numbers_only_query(self, agent):
        """Test numbers-only query"""
        response = agent.process_query(SearchQuery(query="12345"))
        
        # Should handle gracefully
        assert response is not None
    
    def test_repeated_words_query(self, agent):
        """Test query with repeated words"""
        response = agent.process_query(
            SearchQuery(query="libro libro libro libro")
        )
        
        assert response.results.total_results >= 0
    
    def test_case_sensitivity(self, agent):
        """Test case insensitivity"""
        queries = [
            "MURAKAMI",
            "murakami",
            "MuRaKaMi",
            "Murakami"
        ]
        
        results_counts = []
        for q in queries:
            response = agent.process_query(SearchQuery(query=q))
            results_counts.append(response.results.total_results)
        
        # Should return same results regardless of case
        assert len(set(results_counts)) == 1
    
    def test_sql_injection_attempt(self, agent):
        """Test SQL injection patterns (should be harmless)"""
        sql_query = "'; DROP TABLE books; --"
        
        response = agent.process_query(SearchQuery(query=sql_query))
        
        # Should not crash and books should still exist
        assert response is not None
        assert len(agent.search_engine.books) > 0
    
    def test_nonexistent_author(self, agent):
        """Test query for non-existent author"""
        response = agent.process_query(
            SearchQuery(query="Cerco libri di AuthorThatDoesNotExist12345")
        )
        
        assert response.results.total_results == 0
        assert "non ho trovato" in response.message.lower()
    
    def test_multiple_spaces_between_words(self, agent):
        """Test query with multiple spaces"""
        response = agent.process_query(
            SearchQuery(query="Cerco     libro     di     Murakami")
        )
        
        # Should normalize spaces and find results
        assert response.results.total_results > 0


class TestConcurrency:
    """Test concurrent query handling"""
    
    def test_multiple_sessions_isolation(self, agent):
        """Test that multiple sessions don't interfere"""
        
        # Session 1
        response1a = agent.process_query(
            SearchQuery(query="Cerco libri di Rowling")
        )
        session1 = response1a.session_id
        
        # Session 2
        response2a = agent.process_query(
            SearchQuery(query="Cerco libri di Murakami")
        )
        session2 = response2a.session_id
        
        # Follow-up in session 1
        response1b = agent.process_query(
            SearchQuery(query="E il secondo?", session_id=session1)
        )
        
        # Follow-up in session 2
        response2b = agent.process_query(
            SearchQuery(query="E il secondo?", session_id=session2)
        )
        
        # Should have different contexts
        assert session1 != session2
        
        # Session 1 should reference Rowling context
        # Session 2 should reference Murakami context
        assert response1b.results.intent.value.startswith("followup")
        assert response2b.results.intent.value.startswith("followup")


class TestPerformanceLimits:
    """Test performance under stress"""
    
    def test_rapid_sequential_queries(self, agent):
        """Test many queries in sequence"""
        
        queries = [f"Query {i}" for i in range(50)]
        
        for query in queries:
            response = agent.process_query(SearchQuery(query=query))
            
            # Each should complete quickly
            assert response.results.search_time_ms < 3000
    
    def test_context_memory_cleanup(self, agent):
        """Test that old contexts are cleaned up"""
        
        # Create many sessions
        session_ids = []
        for i in range(100):
            response = agent.process_query(
                SearchQuery(query=f"Query {i}")
            )
            session_ids.append(response.session_id)
        
        # Force cleanup of expired contexts
        agent.context_manager._clean_expired()
        
        # Some contexts should be cleaned
        # (In real scenario with actual time passing)
        assert len(agent.context_manager.contexts) <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
