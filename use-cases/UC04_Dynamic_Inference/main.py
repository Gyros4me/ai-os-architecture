import sys
import os

# Ensure the current directory is in the path for dynamic imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.core import InferenceService

def main():
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'clients.json')
    service = InferenceService(config_path)
    
    test_cases = [
        ("client_a", "Sono così CONTENTO oggi!!!"),
        ("client_b", "Ho bisogno di un rimborso per il mio acquisto."),
        ("client_b", "ciao, come va?"),
        ("client_b", "Ho un errore tecnico con il software, aiuto.")
    ]
    
    print("--- Dynamic Inference Service Demo ---")
    for client_id, text in test_cases:
        print(f"\n[Client: {client_id}] Input: '{text}'")
        try:
            result = service.run_inference(client_id, text)
            print(f"Result: {result}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()