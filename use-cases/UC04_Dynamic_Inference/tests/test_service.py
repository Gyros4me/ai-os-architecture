import unittest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core import InferenceService

class TestInferenceService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'clients.json')
        cls.service = InferenceService(config_path)

    def test_client_a_emotion_happy(self):
        # Client A: lowercase, strip_punctuation, add_confidence_score
        result = self.service.run_inference("client_a", "Sono così CONTENTO oggi!!!")
        self.assertEqual(result['prediction'], "contento")
        self.assertIn('confidence', result)
        self.assertEqual(result['confidence'], 0.95)

    def test_client_a_emotion_angry(self):
        result = self.service.run_inference("client_a", "Sono così alterato!!!")
        self.assertEqual(result['prediction'], "alterato")
        self.assertIn('confidence', result)

    def test_client_b_rule_refund(self):
        # Client B: "rimborso" in text + predicted "vendite" -> override to "supporto"
        result = self.service.run_inference("client_b", "Ho bisogno di un rimborso per il mio acquisto.")
        self.assertEqual(result['prediction'], "supporto")

    def test_client_b_rule_short_text(self):
        # Client B: < 20 words + "ciao" + predicted "generic" -> "support"
        result = self.service.run_inference("client_b", "ciao, come va?")
        self.assertEqual(result['prediction'], "supporto")

    def test_client_b_technical_support(self):
        # Should predict "supporto" based on keywords
        result = self.service.run_inference("client_b", "Ho un errore tecnico con il software, aiuto.")
        self.assertEqual(result['prediction'], "supporto")

    def test_invalid_client(self):
        with self.assertRaises(ValueError):
            self.service.run_inference("non_existent", "hello")

if __name__ == '__main__':
    unittest.main()