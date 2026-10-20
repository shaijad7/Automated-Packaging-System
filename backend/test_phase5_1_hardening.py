"""
Focused regression tests for Phase 5.1:
- SEC-01: Fail safely when edge API key is missing, empty, or whitespace; verify no insecure default.
- SEC-02: Correctly parse multiple CORS origins, trim whitespace, ignore empty entries, handle missing/empty safely.
"""

import os
import sys
from pathlib import Path
import pytest
from pydantic import ValidationError
from pydantic_core import PydanticUndefined

# Add backend and project root directory to sys.path
backend_dir = Path(__file__).resolve().parent
project_root = backend_dir.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(project_root))

from app.core.config import parse_cors_origins, settings as backend_settings
from app.main import app
from fastapi.middleware.cors import CORSMiddleware


# =============================================================================
# SEC-01: cv_pipeline/config.py Edge-Node API Key Hardening Tests
# =============================================================================

def test_sec01_valid_edge_api_key_loads():
    """Verify that a valid, configured edge-node API key loads successfully."""
    from cv_pipeline.config import Settings as CvSettings
    
    cv_settings = CvSettings(
        EDGE_NODE_API_KEY="valid-secure-edge-key-sample-12345",
        _env_file=None
    )
    assert cv_settings.EDGE_NODE_API_KEY == "valid-secure-edge-key-sample-12345"
    print("PASS: SEC-01 valid configured edge API key loads successfully")


def test_sec01_missing_edge_api_key_fails_safely():
    """Verify that missing EDGE_NODE_API_KEY causes a safe ValidationError."""
    from cv_pipeline.config import Settings as CvSettings
    
    # Isolate environment to ensure no ambient key is read
    clean_env = {k: v for k, v in os.environ.items() if k != "EDGE_NODE_API_KEY"}
    old_env = os.environ.copy()
    try:
        os.environ.clear()
        os.environ.update(clean_env)
        
        with pytest.raises(ValidationError) as exc_info:
            CvSettings(_env_file=None)
            
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("EDGE_NODE_API_KEY",) and e["type"] == "missing" for e in errors), (
            f"Expected 'missing' error for EDGE_NODE_API_KEY, got: {errors}"
        )
        print("PASS: SEC-01 missing EDGE_NODE_API_KEY fails safely with ValidationError")
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def test_sec01_empty_edge_api_key_fails_safely():
    """Verify that an empty string EDGE_NODE_API_KEY raises a ValidationError."""
    from cv_pipeline.config import Settings as CvSettings
    
    with pytest.raises(ValidationError) as exc_info:
        CvSettings(EDGE_NODE_API_KEY="", _env_file=None)
        
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("EDGE_NODE_API_KEY",) for e in errors)
    print("PASS: SEC-01 empty EDGE_NODE_API_KEY fails safely with ValidationError")


def test_sec01_whitespace_edge_api_key_fails_safely():
    """Verify that a whitespace-only EDGE_NODE_API_KEY raises a ValidationError."""
    from cv_pipeline.config import Settings as CvSettings
    
    with pytest.raises(ValidationError) as exc_info:
        CvSettings(EDGE_NODE_API_KEY="   \t   \n  ", _env_file=None)
        
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("EDGE_NODE_API_KEY",) for e in errors)
    print("PASS: SEC-01 whitespace-only EDGE_NODE_API_KEY fails safely with ValidationError")


def test_sec01_no_insecure_default():
    """Verify that EDGE_NODE_API_KEY has no default value and is strictly required."""
    from cv_pipeline.config import Settings as CvSettings
    
    field = CvSettings.model_fields["EDGE_NODE_API_KEY"]
    assert field.default is PydanticUndefined or field.is_required(), (
        "EDGE_NODE_API_KEY must not have a default fallback value"
    )
    assert field.default != "default_unsafe_key_for_dev", (
        "Insecure default 'default_unsafe_key_for_dev' was detected!"
    )
    print("PASS: SEC-01 no insecure default fallback exists on Settings.EDGE_NODE_API_KEY")


# =============================================================================
# SEC-02: CORS Origins Parsing and Backend Integration Tests
# =============================================================================

def test_sec02_parse_single_origin():
    """Verify that a single origin is parsed correctly without altering the string."""
    result = parse_cors_origins("http://localhost:3000")
    assert result == ["http://localhost:3000"]
    print("PASS: SEC-02 single origin parsed correctly")


def test_sec02_parse_multiple_origins():
    """Verify that multiple comma-separated origins are split into distinct items."""
    raw = "http://localhost:3000,http://127.0.0.1:3000,https://inventory.example.com"
    result = parse_cors_origins(raw)
    assert result == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://inventory.example.com"
    ]
    print("PASS: SEC-02 multiple comma-separated origins parsed correctly")


def test_sec02_whitespace_trimming():
    """Verify that whitespace around origins is trimmed cleanly."""
    raw = "   http://localhost:3000   ,   https://app.example.com\t ,  http://192.168.1.100:3000 \n"
    result = parse_cors_origins(raw)
    assert result == [
        "http://localhost:3000",
        "https://app.example.com",
        "http://192.168.1.100:3000"
    ]
    print("PASS: SEC-02 whitespace around origins is trimmed cleanly")


def test_sec02_empty_entries_ignored():
    """Verify that extra/consecutive commas and empty entries are ignored."""
    raw = "http://localhost:3000,,   ,,https://app.example.com, , "
    result = parse_cors_origins(raw)
    assert result == [
        "http://localhost:3000",
        "https://app.example.com"
    ]
    print("PASS: SEC-02 empty entries and consecutive commas are ignored")


def test_sec02_empty_or_none_handled_safely():
    """Verify that None, empty string, or whitespace string return an empty list (fail-closed)."""
    assert parse_cors_origins("") == []
    assert parse_cors_origins("   ") == []
    assert parse_cors_origins(None) == []
    print("PASS: SEC-02 empty or None origin string fails closed to empty list")


def test_sec02_list_input_handling():
    """Verify that list input is also safely processed and sanitized."""
    raw_list = ["  http://localhost:3000  ", "", "  https://example.com  ", None]
    result = parse_cors_origins(raw_list)
    assert result == ["http://localhost:3000", "https://example.com"]
    print("PASS: SEC-02 list input is safely handled and sanitized")


def test_sec02_backend_settings_property_integration():
    """Verify that settings.cors_origins dynamically parses settings.API_CORS_ORIGINS."""
    original_val = backend_settings.API_CORS_ORIGINS
    try:
        backend_settings.API_CORS_ORIGINS = "http://origin-a.com, http://origin-b.com"
        assert backend_settings.cors_origins == ["http://origin-a.com", "http://origin-b.com"]
        
        backend_settings.API_CORS_ORIGINS = "http://localhost:3000"
        assert backend_settings.cors_origins == ["http://localhost:3000"]
    finally:
        backend_settings.API_CORS_ORIGINS = original_val
    print("PASS: SEC-02 backend settings.cors_origins property integrates correctly")


def test_sec02_main_app_cors_middleware():
    """Verify that the FastAPI app CORSMiddleware receives the parsed list of origins and responds correctly."""
    from fastapi.testclient import TestClient

    cors_middleware = None
    for middleware in app.user_middleware:
        if middleware.cls is CORSMiddleware:
            cors_middleware = middleware
            break
            
    assert cors_middleware is not None, "CORSMiddleware not found in app.user_middleware"
    configured_origins = cors_middleware.kwargs.get("allow_origins", [])
    
    # Must be a list of strings
    assert isinstance(configured_origins, list), f"Expected list of origins, got {type(configured_origins)}"
    # Must not contain wildcard '*'
    assert "*" not in configured_origins, "Wildcard '*' must not be present in allow_origins"
    # Must contain the configured origin
    for o in backend_settings.cors_origins:
        assert o in configured_origins

    # Test actual CORS preflight behavior via TestClient
    client = TestClient(app)
    # Allowed origin gets access-control-allow-origin header
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    # Disallowed origin does NOT get access-control-allow-origin header
    disallowed_response = client.options(
        "/api/health",
        headers={
            "Origin": "http://malicious-attacker.com",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert "access-control-allow-origin" not in disallowed_response.headers
    print("PASS: SEC-02 FastAPI CORSMiddleware correctly configured and enforces parsed origins")


def run_all():
    print("=== RUNNING SEC-01 TESTS ===")
    test_sec01_valid_edge_api_key_loads()
    test_sec01_missing_edge_api_key_fails_safely()
    test_sec01_empty_edge_api_key_fails_safely()
    test_sec01_whitespace_edge_api_key_fails_safely()
    test_sec01_no_insecure_default()

    print("\n=== RUNNING SEC-02 TESTS ===")
    test_sec02_parse_single_origin()
    test_sec02_parse_multiple_origins()
    test_sec02_whitespace_trimming()
    test_sec02_empty_entries_ignored()
    test_sec02_empty_or_none_handled_safely()
    test_sec02_list_input_handling()
    test_sec02_backend_settings_property_integration()
    test_sec02_main_app_cors_middleware()

    print("\nALL PHASE 5.1 FOCUSED REGRESSION TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_all()
