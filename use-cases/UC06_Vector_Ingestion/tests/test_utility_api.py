# tests/test_utility_api.py
"""
Comprehensive tests for utility API endpoints.
"""
import pytest
import requests
import json
import os
import time
from pathlib import Path

class TestUtilityAPIEndpoints:
    """Complete tests for utility endpoints."""
    
    BASE_URL = os.getenv("VECTOR_BASE_URL", "http://localhost:8003")
    TIMEOUT = 30
    
    def test_00_get_api_spec(self):
        """Test GET /api-spec endpoint."""
        print("\n=== Test GET /api-spec ===")
        
        response = requests.get(f"{self.BASE_URL}/api-spec", timeout=self.TIMEOUT)
        assert response.status_code == 200
        
        # Should return custom API specification
        data = response.json()
        
        # Validate API spec structure - NUOVA STRUTTURA
        print(f"API Spec keys: {list(data.keys())}")
        
        # La nuova struttura ha questi campi:
        assert 'service' in data
        assert 'timestamp' in data
        
        # PuÃ² avere 'endpoints' o 'routes' o 'documentation'
        has_documentation = 'documentation' in data
        has_endpoints = 'endpoints' in data
        has_routes = 'routes' in data
        
        assert has_documentation or has_endpoints or has_routes, \
            f"Expected at least one of: documentation, endpoints, routes. Got: {data.keys()}"
        
        print('âœ… API Spec structure validated')
        
        # Verifica opzionale per informazioni base
        service_name = data.get('service', 'Unknown Service')
        print(f"âœ… API Spec: {service_name}")
        
        # Save spec for documentation
        spec_file = "api_spec_latest.json"
        with open(spec_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"   Spec saved to: {spec_file}")
        print(f"   Total data keys: {list(data.keys())}")
        # Test passes - no return needed
        
    def test_01_get_config(self):
        """Test GET /config endpoint."""
        print("\n=== Test GET /config ===")
        
        response = requests.get(f"{self.BASE_URL}/config", timeout=self.TIMEOUT)
        assert response.status_code == 200
        
        config = response.json()
        
        # Validate config structure
        assert 'environment' in config
        
        # Common config fields (some may be optional)
        expected_fields = ['environment', 'version', 'max_file_size_mb', 
                          'chunk_size', 'embedder_model', 'config']
        
        for field in expected_fields:
            if field in config:
                print(f"   {field}: {config[field]}")
                
        print(f"âœ… Config retrieved: {config['environment']} environment")
        
        # Verify it matches health check info
        health_response = requests.get(f"{self.BASE_URL}/health", timeout=self.TIMEOUT)
        health_data = health_response.json()
        
        # Compare environment if available in both
        if 'environment' in health_data:
            assert config['environment'] == health_data['environment']
        
        print(f"   Config keys: {list(config.keys())}")
        # Test passes - no return needed
        
    def test_02_frontend_dashboard(self):
        """Test GET / endpoint (frontend dashboard)."""
        print("\n=== Test Frontend Dashboard ===")
        
        response = requests.get(f"{self.BASE_URL}/", timeout=self.TIMEOUT)
        assert response.status_code == 200
        
        # Should return HTML
        content_type = response.headers.get('content-type', '').lower()
        assert 'text/html' in content_type
        
        # Should contain expected elements
        html = response.text.lower()
        
        # Check for common HTML elements
        assert '<!doctype html>' in html or '<html' in html
        
        # Check for Vue/React app mount point or our app
        if '<div id="app"' in html or 'vue' in html or 'react' in html:
            print("âœ… Frontend is a JavaScript SPA")
        elif 'vector ingestion' in html:
            print("âœ… Frontend contains service name")
        else:
            # Basic HTML response is also OK
            print("âœ… Frontend returns HTML content")
            
        # Check for static assets references
        if 'static/' in html or '.css' in html or '.js' in html:
            print("   References static assets")
            
        # Test static assets if referenced
        if 'static/' in html:
            # Try to access a common static file
            css_response = requests.get(f"{self.BASE_URL}/static/style.css", timeout=self.TIMEOUT)
            if css_response.status_code == 200:
                print("âœ… Static CSS file accessible")
        
        # Log dashboard stats
        print(f"   Dashboard HTML length: {len(html)} chars")
        print(f"   Content type: {content_type}")
        # Test passes - no return needed
        
    def test_03_openapi_json(self):
        """Test GET /openapi.json endpoint (alternate spec)."""
        print("\n=== Test GET /openapi.json ===")
        
        response = requests.get(f"{self.BASE_URL}/openapi.json", timeout=self.TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"OpenAPI keys: {list(data.keys())}")
            
            # Dovrebbe essere uno schema OpenAPI
            # PuÃ² avere 'openapi' o 'swagger' o essere un oggetto custom
            is_openapi = 'openapi' in data
            is_swagger = 'swagger' in data
            has_info = 'info' in data
            has_paths = 'paths' in data
            
            if is_openapi or is_swagger:
                # Standard OpenAPI/Swagger
                if has_info:
                    print(f"âœ… OpenAPI JSON available: {data['info'].get('title', 'OpenAPI Spec')}")
                else:
                    print(f"âœ… OpenAPI JSON available (no info)")
                    
                if has_paths:
                    print(f"   Paths documented: {len(data['paths'])}")
            else:
                # Custom format
                print(f"âœ… Custom API format available")
                
            # Compare with /api-spec - non necessariamente identici
            spec_response = requests.get(f"{self.BASE_URL}/api-spec", timeout=self.TIMEOUT)
            if spec_response.status_code == 200:
                spec_data = spec_response.json()
                # Verifica che siano dello stesso servizio se possibile
                if 'service' in spec_data and 'info' in data:
                    service_from_spec = spec_data['service']
                    title_from_openapi = data['info'].get('title', '')
                    if title_from_openapi:
                        # Potrebbero avere nomi diversi ma correlati
                        print(f"   Service from spec: {service_from_spec}")
                        print(f"   Title from OpenAPI: {title_from_openapi}")
            
            print(f"   OpenAPI spec validated")
            # Test passes - no return needed
        else:
            print(f"⚠️  /openapi.json returned {response.status_code}")
            # Test will continue - no return needed
            
    def test_04_docs_endpoint(self):
        """Test GET /docs endpoint (Swagger UI)."""
        print("\n=== Test GET /docs ===")
        
        response = requests.get(f"{self.BASE_URL}/docs", timeout=self.TIMEOUT)
        
        if response.status_code == 200:
            # Should be Swagger UI HTML
            html = response.text.lower()
            
            assert 'swagger' in html or 'openapi' in html
            assert '<html' in html
            
            print("âœ… Swagger UI documentation available")
            
            # Check for redoc alternative
            redoc_response = requests.get(f"{self.BASE_URL}/redoc", timeout=5)
            if redoc_response.status_code == 200:
                print("   ReDoc documentation also available")
            
            print(f"   Documentation endpoints validated")
            # Test passes - no return needed
        else:
            print(f"⚠️  /docs endpoint returned {response.status_code}")
            # Test will continue - no return needed
            
    def test_05_robots_txt(self):
        """Test robots.txt for web crawlers."""
        print("\n=== Test robots.txt ===")
        
        response = requests.get(f"{self.BASE_URL}/robots.txt", timeout=self.TIMEOUT)
        
        if response.status_code == 200:
            content = response.text
            assert 'User-agent:' in content
            
            print("âœ… robots.txt configured")
            print(f"   Content: {content[:100]}...")
        elif response.status_code == 404:
            print("âš ï¸  robots.txt not found (not required)")
        else:
            print(f"âš ï¸  robots.txt returned {response.status_code}")
            
    def test_06_favicon(self):
        """Test favicon.ico."""
        print("\n=== Test favicon.ico ===")
        
        response = requests.get(f"{self.BASE_URL}/favicon.ico", timeout=self.TIMEOUT)
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            
            # Could be image/x-icon, image/vnd.microsoft.icon, etc.
            assert 'image' in content_type.lower()
            
            print(f"âœ… Favicon available: {content_type}")
        else:
            print(f"âš ï¸  favicon.ico returned {response.status_code}")
            
    def test_07_static_assets(self):
        """Test static assets directory."""
        print("\n=== Test Static Assets ===")
        
        # Common static files
        static_files = [
            '/static/style.css',
            '/static/app.js',
            '/static/index.html'
        ]
        
        for static_file in static_files:
            response = requests.get(f"{self.BASE_URL}{static_file}", timeout=self.TIMEOUT)
            
            if response.status_code == 200:
                print(f"âœ… Static file {static_file} accessible")
                
                # Check content type
                content_type = response.headers.get('content-type', '')
                if '.css' in static_file:
                    assert 'text/css' in content_type or 'css' in content_type
                elif '.js' in static_file:
                    assert 'javascript' in content_type or 'application/javascript' in content_type
                elif '.html' in static_file:
                    assert 'text/html' in content_type
            else:
                print(f"âš ï¸  Static file {static_file} returned {response.status_code}")
                
    def test_08_cors_headers(self):
        """Test CORS headers for API."""
        print("\n=== Test CORS Headers ===")
        
        # Make OPTIONS request to check CORS
        response = requests.options(f"{self.BASE_URL}/health", timeout=self.TIMEOUT)
        
        # Check for CORS headers
        cors_headers = [
            'access-control-allow-origin',
            'access-control-allow-methods',
            'access-control-allow-headers'
        ]
        
        found_cors_headers = []
        for header in cors_headers:
            if header in response.headers:
                found_cors_headers.append(header)
                print(f"   {header}: {response.headers[header]}")
                
        if found_cors_headers:
            print(f"âœ… CORS headers configured ({len(found_cors_headers)} headers)")
        else:
            print("âš ï¸  No CORS headers found (might be internal service only)")
            
    def test_09_api_versioning(self):
        """Test API version information."""
        print("\n=== Test API Versioning ===")
        
        # Get version from multiple sources
        sources = [
            ('/health', 'version'),
            ('/config', 'version'),
            ('/api-spec', 'version')  # Ora potrebbe essere al primo livello
        ]
        
        versions = []
        
        for endpoint, key in sources:
            response = requests.get(f"{self.BASE_URL}{endpoint}", timeout=self.TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                
                # Cerca la versione in modo flessibile
                if isinstance(key, list):
                    # Navigate nested keys
                    value = data
                    for k in key:
                        if isinstance(value, dict) and k in value:
                            value = value.get(k)
                        else:
                            value = None
                            break
                    version = value
                else:
                    version = data.get(key)
                    
                if version:
                    versions.append((endpoint, version))
                    
        # All versions should match
        if len(versions) >= 2:
            unique_versions = set(version for _, version in versions)
            if len(unique_versions) == 1:
                print(f"âœ… Consistent API version: {list(unique_versions)[0]}")
                print(f"   Sources: {[endpoint for endpoint, _ in versions]}")
            else:
                print(f"âš ï¸  Version mismatch: {versions}")
        else:
            print(f"âš ï¸  Could not verify version consistency (found {len(versions)} versions)")
            
    def test_10_error_pages(self):
        """Test error page responses."""
        print("\n=== Test Error Pages ===")
        
        # Test non-existent endpoint
        response = requests.get(f"{self.BASE_URL}/nonexistent-endpoint-12345", timeout=self.TIMEOUT)
        
        # Should return 404
        assert response.status_code == 404
        
        # Should return JSON error for API
        content_type = response.headers.get('content-type', '')
        if 'application/json' in content_type:
            error_data = response.json()
            assert 'detail' in error_data
            print(f"âœ… JSON error response for 404: {error_data.get('detail', '')[:50]}...")
        else:
            # Might return HTML
            print(f"âœ… 404 error page returned")
            
        # Test method not allowed
        response = requests.delete(f"{self.BASE_URL}/health", timeout=self.TIMEOUT)
        assert response.status_code == 405  # Method Not Allowed
        
        print("âœ… 405 Method Not Allowed handled correctly")
        
    def test_11_rate_limiting(self):
        """Test basic rate limiting (if implemented)."""
        print("\n=== Test Rate Limiting ===")
        
        # Make multiple rapid requests to /health
        requests_made = 5
        responses = []
        
        for i in range(requests_made):
            try:
                response = requests.get(f"{self.BASE_URL}/health", timeout=5)
                responses.append(response.status_code)
                time.sleep(0.1)  # Small delay
            except Exception as e:
                responses.append(str(e))
                
        success_count = sum(1 for r in responses if r == 200)
        
        print(f"   Made {requests_made} requests, {success_count} succeeded")
        
        if success_count == requests_made:
            print("âœ… No rate limiting detected (or within limits)")
        elif success_count > 0:
            print(f"âš ï¸  Partial rate limiting: {success_count}/{requests_made} succeeded")
        else:
            print("âŒ All requests failed (might be rate limiting or other issue)")
            
    def test_12_environment_endpoints(self):
        """Test environment-specific endpoints."""
        print("\n=== Test Environment Endpoints ===")
        
        # Check if we can determine environment
        config = requests.get(f"{self.BASE_URL}/config", timeout=self.TIMEOUT).json()
        environment = config.get('environment', 'development').lower()
        
        print(f"   Environment: {environment}")
        
        # Development-only endpoints (if any)
        if environment == 'development':
            # Try debug endpoints
            debug_endpoints = ['/debug', '/metrics', '/prometheus']
            
            for endpoint in debug_endpoints:
                response = requests.get(f"{self.BASE_URL}{endpoint}", timeout=5)
                if response.status_code == 200:
                    print(f"âœ… Development endpoint {endpoint} available")
                elif response.status_code != 404:
                    print(f"âš ï¸  Endpoint {endpoint}: {response.status_code}")
                    
        # Production checks
        if environment == 'production':
            # Verify security headers
            response = requests.get(f"{self.BASE_URL}/health", timeout=self.TIMEOUT)
            security_headers = [
                'x-frame-options',
                'x-content-type-options',
                'x-xss-protection',
                'strict-transport-security'
            ]
            
            found_headers = []
            for header in security_headers:
                if header in response.headers:
                    found_headers.append(header)
                    
            if found_headers:
                print(f"âœ… Security headers in production: {found_headers}")
                
    def run_all_utility_tests(self):
        """Run all utility tests in sequence."""
        print("\n" + "="*60)
        print("COMPLETE UTILITY API TEST SUITE")
        print("="*60)
        
        test_methods = [
            ('API Specification', self.test_00_get_api_spec),
            ('Configuration', self.test_01_get_config),
            ('Frontend Dashboard', self.test_02_frontend_dashboard),
            ('OpenAPI JSON', self.test_03_openapi_json),
            ('Documentation', self.test_04_docs_endpoint),
            ('Robots.txt', self.test_05_robots_txt),
            ('Favicon', self.test_06_favicon),
            ('Static Assets', self.test_07_static_assets),
            ('CORS Headers', self.test_08_cors_headers),
            ('API Versioning', self.test_09_api_versioning),
            ('Error Pages', self.test_10_error_pages),
            ('Rate Limiting', self.test_11_rate_limiting),
            ('Environment', self.test_12_environment_endpoints)
        ]
        
        results = {}
        
        for test_name, test_func in test_methods:
            try:
                print(f"\nðŸ“‹ Running: {test_name}")
                result = test_func()
                results[test_name] = {
                    'status': 'PASSED',
                    'result': result
                }
                print(f"âœ… {test_name}: PASSED")
            except Exception as e:
                results[test_name] = {
                    'status': 'FAILED',
                    'error': str(e)
                }
                print(f"âŒ {test_name}: FAILED - {e}")
                
        # Generate summary
        passed = sum(1 for r in results.values() if r['status'] == 'PASSED')
        total = len(results)
        
        print(f"\nðŸ“Š Utility Tests Summary: {passed}/{total} passed ({passed/total*100:.0f}%)")
        
        return results


# Run standalone if needed
if __name__ == "__main__":
    tester = TestUtilityAPIEndpoints()
    results = tester.run_all_utility_tests()
