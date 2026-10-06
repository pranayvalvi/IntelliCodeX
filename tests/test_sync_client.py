import os
import pytest
from client.sync import build_manifest

def test_build_manifest_empty(tmp_path):
    manifest = build_manifest(str(tmp_path))
    assert manifest == {}

def test_build_manifest_ignores(tmp_path):
    os.makedirs(tmp_path / ".git")
    os.makedirs(tmp_path / "node_modules")
    os.makedirs(tmp_path / "src")
    
    (tmp_path / ".git" / "config").write_text("config")
    (tmp_path / "node_modules" / "lib.js").write_text("lib")
    (tmp_path / "src" / "main.py").write_text("main")
    (tmp_path / "src" / "test.pyc").write_text("binary")
    
    manifest = build_manifest(str(tmp_path))
    assert "src/main.py" in manifest
    assert len(manifest) == 1

def test_build_manifest_hashing(tmp_path):
    import hashlib
    content = b"hello world"
    expected_hash = hashlib.sha256(content).hexdigest()
    
    file_path = tmp_path / "app.py"
    file_path.write_bytes(content)
    
    manifest = build_manifest(str(tmp_path))
    assert manifest["app.py"] == expected_hash
