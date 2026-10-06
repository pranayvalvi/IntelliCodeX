import pytest
from backend.patch_generator.patch_validator import is_test_file, validate_patch
from core.patch_generator import PatchEngine

def test_is_test_file_logic():
    assert is_test_file("test_app.py") is True
    assert is_test_file("tests/app.py") is True
    assert is_test_file("src/app.test.js") is True
    assert is_test_file("app.py") is False
    assert is_test_file("src/main.py") is False

def test_validate_patch_modifies_test_file():
    # Application file
    val = validate_patch(
        patched_code="a = 1",
        git_diff="--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@",
        target_file="app.py"
    )
    assert val.get("modifies_test_file") is False

    # Test file
    val = validate_patch(
        patched_code="a = 1",
        git_diff="--- a/test_app.py\n+++ b/test_app.py\n@@ -1 +1 @@",
        target_file="test_app.py"
    )
    assert val.get("modifies_test_file") is True

    # Multi-file patch with application + test file (target_file is app.py)
    val = validate_patch(
        patched_code="a = 1",
        git_diff="--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n--- a/test_app.py\n+++ b/test_app.py\n@@ -1 +1 @@",
        target_file="app.py"
    )
    assert val.get("modifies_test_file") is True

class MockSandboxRunner:
    def run_tests_with_patch(self, *args, **kwargs):
        from core.sandbox_runner import SandboxTestResult
        return SandboxTestResult(
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            duration_seconds=1.0,
            framework="pytest",
            passed_count=1,
            failed_count=0
        )

class MockLocalizer:
    def __init__(self, target_file):
        self.target_file = target_file
    def localize(self, error_report, top_k=3):
        return {
            "candidates": [{
                "file_path": self.target_file,
                "snippet": "def can_vote(): pass",
                "confidence_score": 0.99
            }]
        }

def test_patch_engine_rejects_test_file(monkeypatch):
    # Mock llm generation to avoid actual LLM calls
    monkeypatch.setattr(
        "core.patch_generator.PatchEngine._generate_fix",
        lambda *args, **kwargs: ("def can_vote(): return True", "explanation", True)
    )
    # Patch reader
    monkeypatch.setattr("core.patch_generator.PatchEngine._read_file", lambda *args, **kwargs: "def can_vote(): pass")
    
    from unittest.mock import MagicMock
    engine = PatchEngine(store=MagicMock(), embedder=MagicMock(), repo_path="/tmp")
    engine.sandbox_runner = MockSandboxRunner()
    
    # 1. Modifies application code -> should be verified (since sandbox is mocked to success)
    engine.localizer = MockLocalizer("app.py")
    res = engine.generate_and_verify_patch(
        repo_id="test",
        error_report="test error",
        max_iterations=1
    )
    assert res["status"] == "verified"
    
    # 2. Modifies test code -> should be rejected and not verified
    engine.localizer = MockLocalizer("test_app.py")
    res2 = engine.generate_and_verify_patch(
        repo_id="test",
        error_report="test error",
        max_iterations=1
    )
    assert res2["status"] == "failed"
    assert res2["sandbox_validation"]["verified"] is False
    assert res2["sandbox_validation"]["test_status"] == "failed"
