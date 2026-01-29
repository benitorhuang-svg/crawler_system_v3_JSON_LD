import os
import pytest
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.parent

def test_root_directory_hygiene():
    """
    SDD Rule: Root directory must only contain specific allowed files and directories.
    No loose scripts allowed.
    """
    allowed_files = {
        "main.py", "pyproject.toml", "uv.lock", "README.md", "Makefile", 
        "Dockerfile", "docker-compose.yml", ".gitignore", ".env", ".env.example"
    }
    # Allow hidden files/dirs generally, but check specifically for .py pollution
    
    root_files = [f.name for f in ROOT_DIR.iterdir() if f.is_file()]
    
    suspicious_python_scripts = []
    for f in root_files:
        if f.endswith(".py") and f not in allowed_files:
            suspicious_python_scripts.append(f)
            
    assert not suspicious_python_scripts, \
        f"SDD Violation: Loose Python scripts found in root: {suspicious_python_scripts}. Move them to 'test/scripts/'."

def test_test_directory_structure():
    """
    SDD Rule: Strict 3-layer test structure (sdd, unit, system).
    """
    test_dir = ROOT_DIR / "test"
    assert test_dir.exists(), "Test directory missing"
    
    expected_dirs = {"sdd", "unit", "system", "scripts", "fixtures"}
    actual_dirs = {d.name for d in test_dir.iterdir() if d.is_dir() and not d.name.startswith("__")}
    
    # It's okay to have extra dirs? No, SDD implies strictness.
    # But we might have 'benchmarks' nested in scripts, so we check top level of test/
    
    extra_dirs = actual_dirs - expected_dirs
    assert not extra_dirs, f"SDD Violation: Unexpected directories in test/: {extra_dirs}"
    
    # Specifically ban 'integration'
    assert not (test_dir / "integration").exists(), "SDD Violation: 'test/integration' should be renamed to 'test/system'."

def test_naming_conventions():
    """
    SDD Rule: Python files must use snake_case.
    """
    for path in ROOT_DIR.rglob("*.py"):
        if ".venv" in str(path) or "__pycache__" in str(path):
            continue
            
        filename = path.name
        if filename == "__init__.py":
            continue
            
        # Basic check for CamelCase or hyphens-in-filenames (which are bad for python imports)
        # We allow snake_case: lowercase words separated by underscores.
        # We assume if it has an uppercase letter, it might be PascalCase (unless it's a constant like SETTINGS.py, but usually files are lowercase)
        
        has_uppercase = any(c.isupper() for c in filename)
        is_snake_case = filename.islower() or not has_uppercase # Loose check, but good start
        
        assert is_snake_case, f"SDD Violation: File '{path.relative_to(ROOT_DIR)}' contains uppercase characters. Use snake_case."

