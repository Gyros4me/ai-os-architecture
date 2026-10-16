#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Command-line interface for Agentic Search Agent
"""
import sys
import io
from typing import Optional

# Force UTF-8 encoding for Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
from .agent import BookSearchAgent, USING_SEMANTIC
from .models import SearchQuery
from .data_loader import generate_sample_books, load_books_from_csv
import os


class CLIInterface:
    def __init__(self, books_data: list, use_semantic: bool = True):
        self.agent = BookSearchAgent(books_data, use_semantic=use_semantic)
        self.current_session_id: Optional[str] = None
        self.use_semantic = use_semantic
    
    def run(self):
        print("=" * 70)
        print("  ðŸ“š AGENTIC SEARCH AGENT - Conversational AI")
        print("=" * 70)
        
        if USING_SEMANTIC and self.use_semantic:
            print("  ðŸ§  SEMANTIC Mode")
        else:
            print("  ðŸ”¤ FUZZY-ONLY Mode")
        
        print(f"  ðŸ“– {len(self.agent.search_engine.books)} books")
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
                    print("\nðŸ‘‹ Arrivederci!")
                    break
                
                if query.lower() == 'stats':
                    stats = self.agent.get_statistics()
                    print(f"\nðŸ“Š Libri: {stats['total_books']} | Sessioni attive: {stats['active_sessions']} | Mode: {stats['mode']}\n")
                    continue
                
                search_query = SearchQuery(query=query, session_id=self.current_session_id)
                response = self.agent.process_query(search_query)
                self.current_session_id = response.session_id
                
                print(f"\nðŸ¤– {response.message}")
                print(f"   ðŸ“Œ Intent: {response.results.intent.value} | Confidence: {response.results.confidence_score:.1f}% | Time: {response.results.search_time_ms:.1f}ms")
                
                if response.results.books:
                    print("\nðŸ“š Risultati:")
                    for i, book in enumerate(response.results.books[:5], 1):
                        authors = ", ".join(book.authors)
                        rating = f"â­ {book.average_rating:.2f}" if book.average_rating else "N/A"
                        print(f"\n{i}. '{book.title}'")
                        print(f"   Autore: {authors}")
                        print(f"   Rating: {rating} ({book.ratings_count:,} recensioni)")
                        if book.publication_date:
                            print(f"   Anno: {book.publication_date}")
                
                if response.suggestions:
                    print(f"\nðŸ’¡ Suggerimenti: {', '.join(response.suggestions)}")
                
                print()
                
            except KeyboardInterrupt:
                print("\n\nðŸ‘‹ Arrivederci!")
                break
            except Exception as e:
                print(f"âŒ Errore: {e}")


def main():
    use_semantic = '--semantic' in sys.argv
    books_csv_path = next((arg for arg in sys.argv[1:] if arg.endswith('.csv') and os.path.exists(arg)), None)
    
    print("\n" + "=" * 70)
    print("  ðŸ“š AGENTIC SEARCH AGENT")
    print("=" * 70)
    
    if USING_SEMANTIC:
        print("  âœ“ Semantic available")
        print(f"  {'ðŸ§  SEMANTIC' if use_semantic else 'ðŸ”¤ FUZZY'} mode")
    else:
        print("  â„¹ï¸  Fuzzy-only")
        use_semantic = False
    
    print("=" * 70 + "\n")
    
    books_data = load_books_from_csv(books_csv_path) if books_csv_path else generate_sample_books()
    
    cli = CLIInterface(books_data, use_semantic=use_semantic)
    cli.run()


if __name__ == "__main__":
    main()