"""
QR Payload Validation Module for Smart Inventory System.

Expected QR payload format:
    INV|<SKU>

Examples of valid payloads:
    - "INV|ADP-001"
    - "INV|BOX_123"
    - "INV|PROD-A-01"

Invalid payloads:
    - None, empty string, non-string
    - "INV|" (missing SKU)
    - "INV|   " (whitespace-only SKU)
    - "INV||001" (malformed pipe)
    - "INV|A|B" (multiple pipes)
    - "INVENTORY|123" (wrong prefix)
"""

import re
from typing import Optional, Tuple, Any

# Prefix required for inventory QR codes
PAYLOAD_PREFIX = "INV|"

# Regex pattern for valid payload:
# Starts with 'INV|', followed by 1 to 64 alphanumeric characters, hyphens, underscores, or dots.
# Allows standard SKU characters while rejecting control chars, spaces, extra pipes, etc.
SKU_PATTERN = re.compile(r"^[A-Za-z0-9_\-\.]{1,64}$")


def validate_qr_payload(payload: Any) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates a QR code payload against the expected INV|<SKU> format.

    Args:
        payload: The raw decoded payload (expected string).

    Returns:
        (is_valid, cleaned_payload, sku):
            - is_valid: True if payload strictly matches INV|<SKU>, False otherwise.
            - cleaned_payload: Normalized string "INV|<SKU>" if valid, else None or raw string.
            - sku: Extracted SKU string if valid, else None.
    """
    if payload is None:
        return False, None, None

    if not isinstance(payload, str):
        return False, None, None

    stripped = payload.strip()
    if not stripped:
        return False, None, None

    # Check prefix
    if not stripped.startswith(PAYLOAD_PREFIX):
        return False, stripped, None

    # Check separator and SKU content
    parts = stripped.split("|")
    if len(parts) != 2:
        # Either no pipe, or multiple pipes
        return False, stripped, None

    prefix, raw_sku = parts
    if prefix != "INV":
        return False, stripped, None

    sku = raw_sku.strip()
    if not sku:
        return False, stripped, None

    # Check SKU character constraints
    if not SKU_PATTERN.match(sku):
        return False, stripped, None

    normalized_payload = f"INV|{sku}"
    return True, normalized_payload, sku


def is_valid_qr_payload(payload: Any) -> bool:
    """Convenience boolean helper for payload validation."""
    is_valid, _, _ = validate_qr_payload(payload)
    return is_valid


def extract_sku(payload: Any) -> Optional[str]:
    """Extracts the SKU from a valid payload, or None if invalid."""
    is_valid, _, sku = validate_qr_payload(payload)
    return sku if is_valid else None
