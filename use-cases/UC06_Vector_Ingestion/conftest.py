"""
Configuration file for pytest.
Sets up test environment and fixtures.
"""
import pytest
import sys
import os
from pathlib import Path
import tempfile
import shutil
import logging
from datetime import datetime

# Configure test logging for verbose output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Test configuration
TEST_BASE_URL = "http://localhost:8003"
TEST_TIMEOUT = 30

@pytest.fixture(scope="session")
def base_url():
    """Fixture for base API URL."""
    return TEST_BASE_URL

@pytest.fixture(scope="session")
def timeout():
    """Fixture for request timeout."""
    return TEST_TIMEOUT

@pytest.fixture(scope="function")
def test_files_dir():
    """Fixture for temporary test files directory."""
    temp_dir = tempfile.mkdtemp(prefix="test_vector_ingestion_")
    yield Path(temp_dir)
    # Cleanup after test
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture(scope="function")
def cleanup_files():
    """Fixture for tracking and cleaning up test files."""
    files_to_clean = []
    yield files_to_clean
    for file_path in files_to_clean:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

@pytest.fixture(scope="function")
def sample_text_content():
    """Fixture for sample text content."""
    return """
    Artificial intelligence (AI) is intelligence demonstrated by machines, 
    as opposed to natural intelligence displayed by animals including humans. 
    Leading AI textbooks define the field as the study of intelligent agents: 
    any system that perceives its environment and takes actions that maximize 
    its chance of achieving its goals.
    """

@pytest.fixture(scope="function")
def sample_csv_content():
    """Fixture for sample CSV content."""
    return """name,age,city,profession
John Doe,30,New York,Engineer
Jane Smith,25,London,Doctor
Bob Johnson,35,Tokyo,Teacher
Alice Brown,28,Paris,Designer
"""

@pytest.fixture(scope="function")
def create_test_pdf():
    """Fixture to create a simple test PDF."""
    def _create_pdf(filename, content="Test PDF content"):
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        
        c = canvas.Canvas(filename, pagesize=letter)
        c.drawString(100, 750, content)
        c.save()
        return filename
    
    return _create_pdf

# Pytest configuration
def pytest_configure(config):
    """Pytest configuration hook."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "security: mark test as security test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance test"
    )

# Asyncio configuration is now set via pytest.ini file

# ============================================================================
# LOGGING FIXTURES FOR VERBOSE TEST OUTPUT
# ============================================================================

@pytest.fixture(scope="function", autouse=True)
def log_test_execution(request):
    """Automatically log test start and end."""
    test_name = request.node.name
    logger.info(f"\n{'='*70}")
    logger.info(f"▶️  START: {test_name}")
    logger.info(f"⏰  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"{'='*70}")
    
    yield
    
    # Log test result
    if hasattr(request.node, 'rep_call') and request.node.rep_call.failed:
        logger.error(f"❌ FAILED: {test_name}")
    else:
        logger.info(f"✅ PASSED: {test_name}")
    logger.info(f"{'='*70}\n")

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Hook to capture test results for logging."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)

@pytest.fixture
def log_metric():
    """Fixture to log metrics during test execution."""
    def _log(name, value):
        logger.info(f"   📊 {name}: {value}")
    return _log

@pytest.fixture
def log_validation():
    """Fixture to log validation checkpoints."""
    def _log(message):
        logger.info(f"   ✓ {message}")
    return _log

@pytest.fixture
def log_data():
    """Fixture to log structured data."""
    def _log(label, data, max_length=200):
        data_str = str(data)
        if len(data_str) > max_length:
            data_str = data_str[:max_length] + "..."
        logger.info(f"   📋 {label}: {data_str}")
    return _log