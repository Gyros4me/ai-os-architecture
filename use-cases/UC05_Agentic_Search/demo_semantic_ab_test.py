"""
Demo A/B Test: Semantic vs Fuzzy Search
Salvare come: demo_semantic_ab_test.py nella root del progetto
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.agent import BookSearchAgent
from src.models import SearchQuery
from src.data_loader import generate_sample_books


def test_query(agent, query, mode):
    response = agent.process_query(SearchQuery(query=query))
    print(f"[{mode}] {query}")
    print(f"  → Confidence: {response.results.confidence_score:.1f}%")
    print(f"  → Results: {response.results.total_results}")
    if response.results.books:
        print(f"  → Top: {response.results.books[0].title}")
    print()
    return response.results.confidence_score


def main():
    print("=" * 70)
    print("  🔬 A/B TEST: Semantic vs Fuzzy-Only")
    print("=" * 70 + "\n")
    
    books = generate_sample_books()
    
    test_cases = [
        "libro triste sulla solitudine",  # Semantic advantage
        "storia d'amore romantica",        # Synonyms
        "avventura fantasy epica",         # Thematic
        "Muradami",                        # Fuzzy advantage (typo)
        "libro eco",                       # Edge case
    ]
    
    # Test SEMANTIC
    print("🧠 SEMANTIC SEARCH\n" + "-" * 70)
    try:
        agent_sem = BookSearchAgent(books, use_semantic=True)
        sem_scores = [test_query(agent_sem, q, "SEM") for q in test_cases]
    except Exception as e:
        print(f"⚠ Semantic failed: {e}")
        print("Install: pip install sentence-transformers\n")
        sem_scores = [0] * len(test_cases)
    
    # Test FUZZY
    print("\n🔤 FUZZY-ONLY SEARCH\n" + "-" * 70)
    agent_fuz = BookSearchAgent(books, use_semantic=False)
    fuz_scores = [test_query(agent_fuz, q, "FUZ") for q in test_cases]
    
    # Compare
    print("\n" + "=" * 70)
    print("  📊 RESULTS")
    print("=" * 70)
    
    sem_wins = sum(1 for i in range(len(test_cases)) if sem_scores[i] > fuz_scores[i])
    fuz_wins = sum(1 for i in range(len(test_cases)) if fuz_scores[i] > sem_scores[i])
    
    for i, q in enumerate(test_cases):
        winner = "🧠" if sem_scores[i] > fuz_scores[i] else "🔤" if fuz_scores[i] > sem_scores[i] else "🤝"
        print(f"{winner} {q[:50]:<50} | Sem: {sem_scores[i]:>5.1f}% | Fuz: {fuz_scores[i]:>5.1f}%")
    
    print(f"\nSemantic: {sem_wins} wins | Fuzzy: {fuz_wins} wins")
    print("=" * 70)


if __name__ == "__main__":
    main()
