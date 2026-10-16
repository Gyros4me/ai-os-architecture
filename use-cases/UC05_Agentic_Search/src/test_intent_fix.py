"""
Test rapido per verificare che l'intent detection funzioni
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from context_manager import IntentDetector, CONCEPTUAL_KEYWORDS
from models import QueryIntent

def test_intent():
    detector = IntentDetector()
    
    print("=" * 70)
    print("TEST INTENT DETECTION - DOPO FIX")
    print("=" * 70)
    print(f"\nCONCEPTUAL_KEYWORDS caricato: {len(CONCEPTUAL_KEYWORDS)} parole")
    print(f"Contiene 'triste': {'triste' in CONCEPTUAL_KEYWORDS}")
    print(f"Contiene 'azione': {'azione' in CONCEPTUAL_KEYWORDS}")
    print()
    
    test_cases = [
        ("libro triste", QueryIntent.SEARCH_BY_KEYWORD),
        ("libri d'azione", QueryIntent.SEARCH_BY_KEYWORD),
        ("murakami", QueryIntent.SEARCH_BY_AUTHOR),
        ("muradami", QueryIntent.SEARCH_BY_AUTHOR),
        ("libro sole", QueryIntent.SEARCH_BY_TITLE),
        ("libro eco", QueryIntent.SEARCH_BY_AUTHOR),
    ]
    
    print("TEST CASES:")
    print("-" * 70)
    
    all_passed = True
    for query, expected in test_cases:
        detected = detector.detect(query, None)
        status = "✅" if detected == expected else "❌"
        
        if detected != expected:
            all_passed = False
            
        print(f"{status} '{query}'")
        print(f"   Atteso: {expected.value}")
        print(f"   Rilevato: {detected.value}")
        print()
    
    print("=" * 70)
    if all_passed:
        print("✅ TUTTI I TEST PASSATI!")
    else:
        print("❌ ALCUNI TEST FALLITI - CONTROLLA IL FILE context_manager.py")
    print("=" * 70)

if __name__ == "__main__":
    test_intent()
