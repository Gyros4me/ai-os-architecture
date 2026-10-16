#!/usr/bin/env python3
"""
Script per verificare gli endpoint reali del servizio
"""
import requests
import json

BASE_URL = "http://localhost:8003"

def test_endpoint(method, path, data=None, files=None):
    """Testa un endpoint e restituisce il risultato."""
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            response = requests.get(url, timeout=5)
        elif method == "POST":
            if files:
                response = requests.post(url, files=files, data=data, timeout=10)
            else:
                response = requests.post(url, json=data, timeout=10)
        elif method == "DELETE":
            response = requests.delete(url, timeout=5)
        else:
            return None
        
        return {
            "status": response.status_code,
            "content": response.text[:200] if response.text else "",
            "json": response.json() if response.headers.get('content-type', '').startswith('application/json') else None
        }
    except Exception as e:
        return {"error": str(e)}

def main():
    """Testa tutti gli endpoint noti."""
    endpoints = [
        ("GET", "/health"),
        ("GET", "/stats"),
        ("GET", "/dlq/stats"),
        ("GET", "/dlq/failed-chunks"),
        ("GET", "/dlq/failed-files"),
        ("GET", "/documents"),
        ("GET", "/collections"),
        ("GET", "/embeddings/info"),
        ("GET", "/api-spec"),
        ("GET", "/config"),
        ("GET", "/docs"),
        ("GET", "/openapi.json"),
    ]
    
    print("🔍 TEST ENDPOINT REALI")
    print("=" * 60)
    
    for method, path in endpoints:
        result = test_endpoint(method, path)
        if result.get("error"):
            print(f"{method} {path:30} → ❌ ERROR: {result['error']}")
        else:
            print(f"{method} {path:30} → HTTP {result['status']}")
            if result.get("json"):
                print(f"   JSON keys: {list(result['json'].keys())}")

if __name__ == "__main__":
    main()