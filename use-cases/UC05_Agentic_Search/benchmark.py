"""
Performance benchmarking script for Agentic Search Agent
Compares different search strategies and generates metrics
"""
import time
import numpy as np
import sys
import os
from typing import List, Dict

sys.path.insert(0, os.path.dirname(__file__))

from src.agent import BookSearchAgent
from src.models import SearchQuery
from src.data_loader import generate_sample_books


class SearchBenchmark:
    """Benchmark different search strategies"""
    
    def __init__(self, agent: BookSearchAgent):
        self.agent = agent
        self.results = {
            "fuzzy_author": [],
            "fuzzy_title": [],
            "tfidf_keyword": [],
            "hybrid_full": []
        }
    
    def benchmark_query(self, query: str, query_type: str) -> Dict:
        """Benchmark a single query"""
        
        # Hybrid (full agent)
        start = time.time()
        response = self.agent.process_query(SearchQuery(query=query))
        hybrid_time = (time.time() - start) * 1000
        
        results = {
            "query": query,
            "type": query_type,
            "hybrid_time_ms": hybrid_time,
            "results_count": response.results.total_results,
            "confidence": response.results.confidence_score
        }
        
        return results
    
    def run_benchmarks(self) -> Dict:
        """Run comprehensive benchmark suite"""
        
        test_queries = [
            # Fuzzy author queries (typos)
            ("Cerco libri di Muradami", "fuzzy_author"),
            ("Autore Rouling", "fuzzy_author"),
            ("Libri scritti da Tokien", "fuzzy_author"),
            
            # Fuzzy title queries
            ("Libro Hary Poter", "fuzzy_title"),
            ("Cerco Nome dela Rosa", "fuzzy_title"),
            
            # Keyword queries
            ("Libro con parola sole", "keyword"),
            ("Libri oceano", "keyword"),
            ("Fantasy", "keyword"),
            
            # Exact matches
            ("J.K. Rowling", "exact"),
            ("Haruki Murakami", "exact"),
        ]
        
        results_by_type = {
            "fuzzy_author": [],
            "fuzzy_title": [],
            "keyword": [],
            "exact": []
        }
        
        print("🔬 Running Benchmarks...")
        print("=" * 60)
        
        for query, qtype in test_queries:
            result = self.benchmark_query(query, qtype)
            results_by_type[qtype].append(result)
            
            print(f"Query: '{query}'")
            print(f"  Type: {qtype}")
            print(f"  Time: {result['hybrid_time_ms']:.1f}ms")
            print(f"  Results: {result['results_count']}")
            print(f"  Confidence: {result['confidence']:.1f}%")
            print()
        
        # Calculate statistics
        stats = self._calculate_statistics(results_by_type)
        
        return {
            "results": results_by_type,
            "statistics": stats
        }
    
    def _calculate_statistics(self, results_by_type: Dict) -> Dict:
        """Calculate performance statistics"""
        
        stats = {}
        
        for qtype, results in results_by_type.items():
            if not results:
                continue
            
            times = [r['hybrid_time_ms'] for r in results]
            confidences = [r['confidence'] for r in results]
            
            stats[qtype] = {
                "count": len(results),
                "avg_time_ms": np.mean(times),
                "min_time_ms": np.min(times),
                "max_time_ms": np.max(times),
                "p50_time_ms": np.percentile(times, 50),
                "p95_time_ms": np.percentile(times, 95),
                "p99_time_ms": np.percentile(times, 99),
                "avg_confidence": np.mean(confidences),
                "min_confidence": np.min(confidences),
                "max_confidence": np.max(confidences)
            }
        
        # Overall stats
        all_times = []
        all_confidences = []
        
        for results in results_by_type.values():
            all_times.extend([r['hybrid_time_ms'] for r in results])
            all_confidences.extend([r['confidence'] for r in results])
        
        stats['overall'] = {
            "total_queries": len(all_times),
            "avg_time_ms": np.mean(all_times),
            "p50_time_ms": np.percentile(all_times, 50),
            "p95_time_ms": np.percentile(all_times, 95),
            "p99_time_ms": np.percentile(all_times, 99),
            "avg_confidence": np.mean(all_confidences),
            "target_time_ms": 3000,
            "performance_vs_target": f"{(np.mean(all_times) / 3000 * 100):.1f}%"
        }
        
        return stats
    
    def print_statistics(self, stats: Dict):
        """Print formatted statistics"""
        
        print("=" * 60)
        print("📊 BENCHMARK RESULTS")
        print("=" * 60)
        print()
        
        # Per-type stats
        for qtype, qstats in stats.items():
            if qtype == 'overall':
                continue
            
            print(f"🔹 {qtype.upper().replace('_', ' ')}")
            print(f"  Queries: {qstats['count']}")
            print(f"  Avg Time: {qstats['avg_time_ms']:.1f}ms")
            print(f"  P50: {qstats['p50_time_ms']:.1f}ms")
            print(f"  P95: {qstats['p95_time_ms']:.1f}ms")
            print(f"  Avg Confidence: {qstats['avg_confidence']:.1f}%")
            print()
        
        # Overall stats
        overall = stats['overall']
        print("=" * 60)
        print("🎯 OVERALL PERFORMANCE")
        print("=" * 60)
        print(f"Total Queries: {overall['total_queries']}")
        print(f"Average Time: {overall['avg_time_ms']:.1f}ms")
        print(f"P50 Time: {overall['p50_time_ms']:.1f}ms")
        print(f"P95 Time: {overall['p95_time_ms']:.1f}ms")
        print(f"P99 Time: {overall['p99_time_ms']:.1f}ms")
        print(f"Target: {overall['target_time_ms']}ms")
        print(f"Performance: {overall['performance_vs_target']} of target")
        print()
        
        # Success indicators
        if overall['p95_time_ms'] < 3000:
            print("✅ P95 under 3000ms target!")
        else:
            print("❌ P95 exceeds 3000ms target")
        
        if overall['avg_time_ms'] < 100:
            print("✅ Excellent average latency (<100ms)")
        elif overall['avg_time_ms'] < 500:
            print("✅ Good average latency (<500ms)")
        
        print()


def main():
    """Run benchmark suite"""
    
    print("=" * 60)
    print("  📊 AGENTIC SEARCH AGENT - Performance Benchmark")
    print("=" * 60)
    print()
    
    # Initialize
    print("Initializing agent...")
    books_data = generate_sample_books()
    agent = BookSearchAgent(books_data)
    print(f"✅ Loaded {len(books_data)} books\n")
    
    # Run benchmarks
    benchmark = SearchBenchmark(agent)
    results = benchmark.run_benchmarks()
    
    # Print statistics
    benchmark.print_statistics(results['statistics'])
    
    print("=" * 60)
    print("✅ Benchmark completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
