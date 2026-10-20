import pytest
from qr.payload_validator import validate_qr_payload, is_valid_qr_payload, extract_sku


class TestQRPayloadValidation:
    """Test suite for Phase 4: Strict QR Payload Validation (INV|<SKU>)."""

    def test_valid_standard_payloads(self):
        valid_cases = [
            ("INV|ADP-001", "ADP-001"),
            ("INV|BOX_123", "BOX_123"),
            ("INV|ITEM.456", "ITEM.456"),
            ("INV|A", "A"),
            ("INV|SKU-2026-X", "SKU-2026-X"),
            ("  INV|ADP-001  ", "ADP-001"),  # whitespace stripping
        ]
        for payload, expected_sku in valid_cases:
            is_valid, norm_payload, sku = validate_qr_payload(payload)
            assert is_valid is True, f"Failed for {payload}"
            assert norm_payload == f"INV|{expected_sku}"
            assert sku == expected_sku
            assert is_valid_qr_payload(payload) is True
            assert extract_sku(payload) == expected_sku

    def test_invalid_payload_empty_and_types(self):
        invalid_types = [
            None,
            "",
            "   ",
            123,
            ["INV|ADP-001"],
            {"payload": "INV|ADP-001"},
            True,
            False,
        ]
        for val in invalid_types:
            is_valid, norm, sku = validate_qr_payload(val)
            assert is_valid is False
            assert sku is None
            assert is_valid_qr_payload(val) is False
            assert extract_sku(val) is None

    def test_invalid_missing_or_whitespace_sku(self):
        bad_skus = [
            "INV|",
            "INV|   ",
            "INV|\t",
            "INV|\n",
            "INV|  \t  ",
        ]
        for payload in bad_skus:
            is_valid, _, sku = validate_qr_payload(payload)
            assert is_valid is False, f"Should reject empty SKU: {payload}"
            assert sku is None

    def test_invalid_prefix(self):
        bad_prefixes = [
            "INVENTORY|ADP-001",
            "inv|ADP-001",  # lowercase
            "Inv|ADP-001",
            "PROD|ADP-001",
            "ADP-001",
            "|ADP-001",
        ]
        for payload in bad_prefixes:
            is_valid, _, sku = validate_qr_payload(payload)
            assert is_valid is False, f"Should reject invalid prefix: {payload}"
            assert sku is None

    def test_invalid_separators(self):
        bad_separators = [
            "INV||ADP-001",  # double pipe
            "INV|ADP|001",  # multiple pipes
            "INV-ADP-001",  # dash instead of pipe
            "INV:ADP-001",  # colon instead of pipe
            "INV/ADP-001",
        ]
        for payload in bad_separators:
            is_valid, _, sku = validate_qr_payload(payload)
            assert is_valid is False, f"Should reject invalid separators: {payload}"
            assert sku is None

    def test_invalid_characters_in_sku(self):
        bad_chars = [
            "INV|SKU 123",  # space inside SKU
            "INV|SKU$123",  # special symbol
            "INV|SKU#123",
            "INV|SKU*123",
            "INV|SKU\x00123",  # null byte
        ]
        for payload in bad_chars:
            is_valid, _, sku = validate_qr_payload(payload)
            assert is_valid is False, f"Should reject disallowed SKU characters: {payload}"
            assert sku is None
