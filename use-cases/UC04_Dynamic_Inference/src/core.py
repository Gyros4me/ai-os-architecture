import json
import importlib
from typing import Any, Dict, List

class InferenceService:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.clients_config = json.load(f)
        self.loaded_clients = {}

    def get_client_config(self, client_id: str) -> Dict:
        if client_id not in self.clients_config:
            raise ValueError(f"Client {client_id} not found in configuration.")
        return self.clients_config[client_id]

    def run_inference(self, client_id: str, input_text: str) -> Dict[str, Any]:
        config = self.get_client_config(client_id)
        
        # 1. Pre-processing
        processed_text = input_text
        for proc_name in config.get('preprocessing', []):
            processed_text = self._apply_processor(proc_name, processed_text)
            
        # 2. Prediction (Mocked for this exercise)
        prediction = self._get_model_prediction(config['model'], processed_text)
        
        # 3. Post-processing
        result = {"prediction": prediction, "original_input": input_text}
        for post_name in config.get('postprocessing', []):
            result = self._apply_processor(post_name, result)
            
        # 4. Rules Engine
        final_prediction = self._apply_rules(config.get('rules', []), processed_text, result['prediction'])
        result['prediction'] = final_prediction
        
        return result

    def _apply_processor(self, name: str, data: Any) -> Any:
        # Dynamic loading of processors
        try:
            module = importlib.import_module(f"src.processors")
            processor_func = getattr(module, name)
            return processor_func(data)
        except (ImportError, AttributeError):
            print(f"Warning: Processor {name} not found. Skipping.")
            return data

    def _get_model_prediction(self, model_config: Dict, text: str) -> str:
        # In a real scenario, this would load a specific model class
        model_type = model_config['type']
        classes = model_config['classes']
        
        # Simple mock logic: pick a class based on text content
        # Note: text here is already preprocessed (lowercase, punctuation removed)
        if model_type == "mock_emotion":
            if "alterato" in text or "arrabbiato" in text or "furioso" in text:
                return "alterato"
            if "contento" in text or "felice" in text or "gioia" in text:
                return "contento"
            return "triste"
        elif model_type == "mock_ticket":
            if "rimborso" in text or "soldi" in text or "comprare" in text or "acquisto" in text:
                return "vendite"
            if "aiuto" in text or "errore" in text or "tecnico" in text or "problema" in text:
                return "supporto"
            return "generico"
        return classes[0]

    def _apply_rules(self, rules: List[Dict], text: str, current_prediction: str) -> str:
        from src.rules import RuleEngine
        engine = RuleEngine(rules)
        return engine.apply(text, current_prediction)
