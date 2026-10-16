from typing import List, Dict, Any

class RuleEngine:
    def __init__(self, rules: List[Dict]):
        self.rules = rules

    def apply(self, text: str, current_prediction: str) -> str:
        new_prediction = current_prediction
        
        for rule in self.rules:
            condition_met = False
            params = rule.get('params', {})
            
            if rule['condition'] == 'contains_word':
                word = params.get('word')
                if_predicted = params.get('if_predicted')
                if word in text and (if_predicted is None or current_prediction == if_predicted):
                    condition_met = True
            
            elif rule['condition'] == 'short_text_with_keywords':
                max_words = params.get('max_words', 100)
                keywords = params.get('keywords', [])
                if_predicted = params.get('if_predicted')
                
                word_count = len(text.split())
                has_keyword = any(kw in text for kw in keywords)
                
                if word_count < max_words and has_keyword and (if_predicted is None or current_prediction == if_predicted):
                    condition_met = True
            
            if condition_met:
                if rule['action'] == 'override':
                    new_prediction = rule['new_value']
                    # Once a rule overrides, we might want to stop or continue. 
                    # For this simple version, we'll allow subsequent rules to also apply.
        
        return new_prediction
