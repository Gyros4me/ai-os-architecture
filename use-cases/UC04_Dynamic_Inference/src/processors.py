import string

def lowercase(text: str) -> str:
    return text.lower()

def strip_punctuation(text: str) -> str:
    return text.translate(str.maketrans('', '', string.punctuation))

def add_confidence_score(result: dict) -> dict:
    # Mock adding a confidence score
    result['confidence'] = 0.95
    return result
