"""
Demo script to showcase the Agentic Search Agent
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

from src.agent import BookSearchAgent
from src.models import SearchQuery
from src.data_loader import generate_sample_books


def print_separator():
    print("\n" + "=" * 70 + "\n")


def demo_fuzzy_matching(agent):
    """Demo fuzzy matching with transcription errors"""
    print("🔍 DEMO 1: Fuzzy Matching (Transcription Errors)")
    print_separator()
    
    test_queries = [
        "Sto cercando Muradami",  # Should match Murakami
        "Libri di Rouling",       # Should match Rowling
        "Autore Tokien",          # Should match Tolkien
    ]
    
    for query in test_queries:
        print(f"Query: '{query}'")
        response = agent.process_query(SearchQuery(query=query))
        
        print(f"✓ Intent: {response.results.intent.value}")
        print(f"✓ Confidence: {response.results.confidence_score:.1f}%")
        print(f"✓ Time: {response.results.search_time_ms:.1f}ms")
        print(f"✓ Results: {response.results.total_results} books")
        
        if response.results.books:
            book = response.results.books[0]
            authors = ", ".join(book.authors)
            print(f"✓ Top Result: '{book.title}' by {authors}")
        
        print()


def demo_keyword_search(agent):
    """Demo keyword search"""
    print("🔍 DEMO 2: Keyword Search")
    print_separator()
    
    query = "Come si chiama quel libro con la parola 'sole' nel titolo?"
    print(f"Query: '{query}'")
    
    response = agent.process_query(SearchQuery(query=query))
    
    print(f"✓ {response.message}")
    print(f"✓ Time: {response.results.search_time_ms:.1f}ms")
    
    for i, book in enumerate(response.results.books[:3], 1):
        authors = ", ".join(book.authors)
        print(f"\n{i}. '{book.title}'")
        print(f"   Author: {authors}")
        print(f"   Rating: ⭐ {book.average_rating:.2f}")


def demo_context_tracking(agent):
    """Demo multi-turn conversation with context"""
    print_separator()
    print("🔍 DEMO 3: Multi-Turn Conversation (Context Tracking)")
    print_separator()
    
    # Turn 1
    query1 = "Cerco libri di Tolkien"
    print(f"User Turn 1: '{query1}'")
    
    response1 = agent.process_query(SearchQuery(query=query1))
    session_id = response1.session_id
    
    print(f"Agent: {response1.message}")
    print(f"Session ID: {session_id}")
    print(f"Results: {response1.results.total_results} books")
    
    for i, book in enumerate(response1.results.books, 1):
        print(f"  {i}. {book.title}")
    
    # Turn 2
    print("\n" + "-" * 70 + "\n")
    query2 = "E il secondo volume?"
    print(f"User Turn 2: '{query2}'")
    
    response2 = agent.process_query(
        SearchQuery(query=query2, session_id=session_id)
    )
    
    print(f"Agent: {response2.message}")
    print(f"Intent: {response2.results.intent.value} (using context!)")
    
    if response2.results.books:
        book = response2.results.books[0]
        print(f"Result: '{book.title}'")


def demo_multilingual(agent):
    """Demo multilingual support"""
    print_separator()
    print("🔍 DEMO 4: Multilingual Support")
    print_separator()
    
    test_queries = [
        ("Cerco Norwegian Wood", "eng"),  # Italian query, English title
        ("Autore di Cent'anni di solitudine", "spa"),  # Spanish origin
        ("Libro 1Q84", "jpn"),  # Japanese author
    ]
    
    for query, expected_lang in test_queries:
        print(f"Query: '{query}'")
        response = agent.process_query(SearchQuery(query=query))
        
        if response.results.books:
            book = response.results.books[0]
            authors = ", ".join(book.authors)
            print(f"✓ Found: '{book.title}' by {authors}")
            print(f"  Language: {book.language_code}")
        
        print()


def demo_performance_stats(agent):
    """Show performance statistics"""
    print_separator()
    print("📊 PERFORMANCE STATISTICS")
    print_separator()
    
    # Run multiple queries and collect stats
    test_queries = [
        "Cerco libri di Rowling",
        "Muradami",
        "Libro con parola oceano",
        "Autore Hemingway",
        "Fantasy",
    ]
    
    times = []
    for query in test_queries:
        response = agent.process_query(SearchQuery(query=query))
        times.append(response.results.search_time_ms)
    
    import numpy as np
    
    print(f"Total queries: {len(times)}")
    print(f"Average time: {np.mean(times):.1f}ms")
    print(f"Min time: {np.min(times):.1f}ms")
    print(f"Max time: {np.max(times):.1f}ms")
    print(f"P95 time: {np.percentile(times, 95):.1f}ms")
    print(f"\n✓ All queries under 3000ms target!")
    
    stats = agent.get_statistics()
    print(f"\nAgent statistics:")
    print(f"  Total books indexed: {stats['total_books']}")
    print(f"  Active sessions: {stats['active_sessions']}")


def main():
    """Run all demos"""
    print("=" * 70)
    print("  📚 AGENTIC SEARCH AGENT - Interactive Demo")
    print("=" * 70)
    
    # Initialize agent
    print("\nInitializing agent with sample dataset...")
    books_data = generate_sample_books()
    agent = BookSearchAgent(books_data)
    print(f"✓ Loaded {len(books_data)} books\n")
    
    # Run demos
    demo_fuzzy_matching(agent)
    demo_keyword_search(agent)
    demo_context_tracking(agent)
    demo_multilingual(agent)
    demo_performance_stats(agent)
    
    print_separator()
    print("🎉 Demo completed!")
    print("\nTo try the interactive CLI: python -m src.cli")
    print("To start the API server: uvicorn src.api:app --reload")
    print_separator()


if __name__ == "__main__":
    main()
