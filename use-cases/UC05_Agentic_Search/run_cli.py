#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Launcher per CLI - FORZA path corretto
"""
import sys
import os

# FORZA no bytecode
sys.dont_write_bytecode = True

# FORZA path corretto
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, 'src')

# Rimuovi eventuali path conflittuali
sys.path = [p for p in sys.path if 'agentic-search' not in p or p == project_root]

# Inserisci path corretto come PRIMO
sys.path.insert(0, project_root)
sys.path.insert(0, src_path)

print(f"📁 Loading from: {src_path}")

# Import dopo aver fixato il path
from src.agent import BookSearchAgent, USING_SEMANTIC
from src.models import SearchQuery
from src.data_loader import generate_sample_books, load_books_from_csv
from src.context_manager import IntentDetector, CONCEPTUAL_KEYWORDS

# Verifica che sia la versione giusta
print(f"✅ CONCEPTUAL_KEYWORDS: {len(CONCEPTUAL_KEYWORDS)} parole")

from typing import Optional

class CLIInterface:
    def __init__(self, books_data: list, use_semantic: bool = True):
        self.agent = BookSearchAgent(books_data, use_semantic=use_semantic)
        self.current_session_id: Optional[str] = None
        self.use_semantic = use_semantic
    
    def run(self):
        print("=" * 70)
        print("  📚 AGENTIC SEARCH AGENT - Conversational AI")
        print("=" * 70)
        
        if USING_SEMANTIC and self.use_semantic:
            print("  🧠 SEMANTIC Mode")
        else:
            print("  🔤 FUZZY-ONLY Mode")
        
        print(f"  📖 {len(self.agent.search_engine.books)} books")
        print("=" * 70)
        
        print("\nEsempi: 'libri di Tolkien', 'libro rosa', 'e il secondo?'")
        print("Comandi: exit, stats")
        print()
        
        while True:
            try:
                query = input("Tu: ").strip()
                
                if not query:
                    continue
                
                if query.lower() in ['exit', 'quit']:
                    print("\n👋 Arrivederci!")
                    break
                
                if query.lower() == 'stats':
                    stats = self.agent.get_statistics()
                    print(f"\n📊 Libri: {stats['total_books']} | Sessioni attive: {stats['active_sessions']} | Mode: {stats['mode']}\n")
                    continue
                
                search_query = SearchQuery(query=query, session_id=self.current_session_id)
                response = self.agent.process_query(search_query)
                self.current_session_id = response.session_id
                
                print(f"\n🤖 {response.message}")
                print(f"   📌 Intent: {response.results.intent.value} | Confidence: {response.results.confidence_score:.1f}% | Time: {response.results.search_time_ms:.1f}ms")
                
                if response.results.books:
                    print("\n📚 Risultati:")
                    for i, book in enumerate(response.results.books[:5], 1):
                        authors = ", ".join(book.authors)
                        rating = f"⭐ {book.average_rating:.2f}" if book.average_rating else "N/A"
                        print(f"\n{i}. '{book.title}'")
                        print(f"   Autore: {authors}")
                        print(f"   Rating: {rating} ({book.ratings_count:,} recensioni)")
                        if book.publication_date:
                            print(f"   Anno: {book.publication_date}")
                
                if response.suggestions:
                    print(f"\n💡 Suggerimenti: {', '.join(response.suggestions)}")
                
                print()
                
            except KeyboardInterrupt:
                print("\n\n👋 Arrivederci!")
                break
            except Exception as e:
                import traceback
                print(f"❌ Errore: {e}")
                traceback.print_exc()


def main():
    use_semantic = '--semantic' in sys.argv or '-s' in sys.argv
    use_fuzzy = '--fuzzy' in sys.argv or '-f' in sys.argv
    
    if use_fuzzy:
        use_semantic = False
    
    books_csv_path = next((arg for arg in sys.argv[1:] if arg.endswith('.csv') and os.path.exists(arg)), None)
    
    print("\n" + "=" * 70)
    print("  📚 AGENTIC SEARCH AGENT")
    print("=" * 70)
    
    if USING_SEMANTIC:
        print("  ✓ Semantic available")
        print(f"  {'🧠 SEMANTIC' if use_semantic else '🔤 FUZZY'} mode")
    else:
        print("  ℹ️  Fuzzy-only")
        use_semantic = False
    
    print("=" * 70 + "\n")
    
    books_data = load_books_from_csv(books_csv_path) if books_csv_path else generate_sample_books()
    
    cli = CLIInterface(books_data, use_semantic=use_semantic)
    cli.run()


if __name__ == "__main__":
    main()
