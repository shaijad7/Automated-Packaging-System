import pytest
import asyncio
from unittest.mock import AsyncMock

from app.db.mongodb import validate_test_db_name, safe_drop_test_database, UNSAFE_TEST_DB_NAMES


def test_reject_production_database_names():
    """Confirms that production and default database names are rejected by validation."""
    for unsafe in UNSAFE_TEST_DB_NAMES:
        with pytest.raises(ValueError, match="Unsafe database target rejected"):
            validate_test_db_name(unsafe)
            
        with pytest.raises(ValueError, match="Unsafe database target rejected"):
            validate_test_db_name(unsafe.upper())


def test_reject_names_without_test_substring():
    """Confirms that database names lacking 'test' are rejected to prevent un-isolated execution."""
    invalid_targets = [
        "inventory",
        "smart_inventory_prod",
        "live_warehouse",
        "stage_inventory",
        "",
        "   ",
    ]
    for target in invalid_targets:
        with pytest.raises(ValueError):
            validate_test_db_name(target)


def test_accept_explicit_test_database_names():
    """Confirms that properly isolated test database names are accepted."""
    valid_targets = [
        "smart_inventory_test_auth",
        "smart_inventory_test_phase10b",
        "smart_inventory_test_reg",
        "smart_inventory_test_phase14",
        "test_isolated_db",
    ]
    for target in valid_targets:
        assert validate_test_db_name(target) == target


def test_safe_drop_blocks_unsafe_targets():
    """Confirms that safe_drop_test_database rejects production names without sending drop commands."""
    mock_client = AsyncMock()
    
    with pytest.raises(ValueError, match="Unsafe database target rejected"):
        asyncio.run(safe_drop_test_database(mock_client, "smart_inventory"))
        
    mock_client.drop_database.assert_not_called()


def test_safe_drop_executes_for_valid_test_targets():
    """Confirms that safe_drop_test_database permits dropping verified test databases."""
    mock_client = AsyncMock()
    test_db = "smart_inventory_test_unit"
    
    asyncio.run(safe_drop_test_database(mock_client, test_db))
    mock_client.drop_database.assert_called_once_with(test_db)


if __name__ == "__main__":
    test_reject_production_database_names()
    test_reject_names_without_test_substring()
    test_accept_explicit_test_database_names()
    test_safe_drop_blocks_unsafe_targets()
    test_safe_drop_executes_for_valid_test_targets()
    print("All database safety guardrail regression tests passed!")
