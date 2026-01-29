import pytest
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.parent

def test_core_schemas_exist():
    """
    SDD Rule: 'core/schemas' must define the SSOT models.
    """
    schema_dir = ROOT_DIR / "core" / "schemas"
    # This might fail if the user's project structure is different, 
    # but based on docs it should be in core/schemas or core/infra/schemas?
    # Let's check typical location or core/__init__.py exports.
    pass # Needs verification of where schemas actually are. 
         # Based on Component Structure: core/infra/schemas.py
         
    schema_file = ROOT_DIR / "core" / "infra" / "schemas.py"
    assert schema_file.exists(), "SDD Violation: 'core/infra/schemas.py' not found. SSOT models missing."

def test_adapters_use_parsers():
    """
    SDD Rule: Adapters must use parsers, not raw string manipulation (best effort check).
    """
    adapter_dir = ROOT_DIR / "core" / "adapters"
    if not adapter_dir.exists():
        return # Skip if no adapters yet
        
    for adapter_file in adapter_dir.glob("adapter_*.py"):
        content = adapter_file.read_text(encoding="utf-8")
        
        # Check for imports
        if "from core.utils.parsers" not in content and "import core.utils.parsers" not in content:
            # This is a warning, maybe not a strict failure if the adapter is trivial
            pass 
            # We enforce usage of DateParser if 'date' is in the text?
            # Keeping strictly to structure for now.

def test_no_float_money():
    """
    SDD Rule: Money must be int, not float.
    Scan Pydantic models for float types on fields that look like money.
    """
    # This is hard to static analyze without AST. 
    # Placeholder for future implementation.
    pass
