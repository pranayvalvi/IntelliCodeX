import pytest
import base64
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app

@pytest.fixture
def sync_client():
    return TestClient(app)

@pytest.fixture
def auth_headers(sync_client):
    res = sync_client.post("/api/auth/register", json={"username": "repuser", "password": "pwd", "email": "r@r.com", "role": "developer"})
    res = sync_client.post("/api/auth/login", json={"username": "repuser", "password": "pwd"})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_remote_bug_localize(sync_client, auth_headers):
    # Setup project and repo
    res_proj = sync_client.post("/api/projects", json={"name": "Bug Proj"}, headers=auth_headers)
    project_id = res_proj.json()["project_id"]
    res_repo = sync_client.post(f"/api/projects/{project_id}/repositories", json={"name": "Bug Repo", "source_path": "/x"}, headers=auth_headers)
    repo_id = res_repo.json()["repository_id"]
    
    # Upload some code
    b64_a = base64.b64encode(b"def compute_magic(): return 42\n").decode("utf-8")
    sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/upload", json={
        "files": [{"path": "magic.py", "content": b64_a}]
    }, headers=auth_headers)
    
    # Index it
    res_idx = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/index", json={"backend": "tfidf"}, headers=auth_headers)
    assert res_idx.status_code == 200
    
    # Test bug localization
    res_loc = sync_client.post("/api/bugs/localize", json={
        "project_id": project_id,
        "repo_id": repo_id,
        "error_report": "compute_magic is returning the wrong value",
        "top_k": 3
    }, headers=auth_headers)
    
    assert res_loc.status_code == 200
    data = res_loc.json()
    assert "candidates" in data
    assert len(data["candidates"]) > 0
    assert "magic.py" in data["candidates"][0]["file_path"]

@patch("core.patch_generator.PatchEngine._generate_fix")
@patch("core.sandbox_runner.SandboxRunner.run_tests_with_patch")
def test_remote_patch_generation(mock_run_tests, mock_generate_fix, sync_client, auth_headers):
    # Setup project and repo
    res_proj = sync_client.post("/api/projects", json={"name": "Patch Proj"}, headers=auth_headers)
    project_id = res_proj.json()["project_id"]
    res_repo = sync_client.post(f"/api/projects/{project_id}/repositories", json={"name": "Patch Repo", "source_path": "/x"}, headers=auth_headers)
    repo_id = res_repo.json()["repository_id"]
    
    # Upload some code
    b64_a = base64.b64encode(b"def compute_magic(): return 42\n").decode("utf-8")
    sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/upload", json={
        "files": [{"path": "magic.py", "content": b64_a}]
    }, headers=auth_headers)
    
    # Index it
    sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/index", json={"backend": "tfidf"}, headers=auth_headers)
    
    # Setup mocks
    mock_generate_fix.return_value = ("def compute_magic(): return 43\n", "Fixed magic", True)
    
    from core.sandbox_runner import SandboxTestResult
    mock_run_tests.return_value = SandboxTestResult(
        success=True,
        exit_code=0,
        stdout="1 passed",
        stderr="",
        duration_seconds=0.1,
        framework="pytest",
        passed_count=1,
        failed_count=0
    )

    # Test patch generation
    res_patch = sync_client.post("/api/patches/generate", json={
        "project_id": project_id,
        "repo_id": repo_id,
        "error_report": "make magic 43",
        "verify_in_sandbox": True
    }, headers=auth_headers)
    
    assert res_patch.status_code == 200
    data = res_patch.json()
    assert data["status"] == "verified"
    assert "return 43" in data["suggested_patch"]
    
    # Verify sandbox runner was called with the project-isolated path, not the original /x
    mock_run_tests.assert_called_once()
    called_kwargs = mock_run_tests.call_args[1]
    assert ".storage" in called_kwargs["repo_path"]
    assert "repository" in called_kwargs["repo_path"]
    assert called_kwargs["repo_path"] != "/x"

def test_unauthorized_localization(sync_client, auth_headers):
    # Setup project and repo as normal user
    res_proj = sync_client.post("/api/projects", json={"name": "Auth Proj"}, headers=auth_headers)
    project_id = res_proj.json()["project_id"]
    res_repo = sync_client.post(f"/api/projects/{project_id}/repositories", json={"name": "Auth Repo", "source_path": "/x"}, headers=auth_headers)
    repo_id = res_repo.json()["repository_id"]
    
    # Login as another user
    sync_client.post("/api/auth/register", json={"username": "hacker", "password": "pwd", "email": "h@h.com", "role": "developer"})
    res_login = sync_client.post("/api/auth/login", json={"username": "hacker", "password": "pwd"})
    hacker_token = res_login.json()["access_token"]
    hacker_headers = {"Authorization": f"Bearer {hacker_token}"}
    
    # Hacker tries to localize
    res_loc = sync_client.post("/api/bugs/localize", json={
        "project_id": project_id,
        "repo_id": repo_id,
        "error_report": "hack me"
    }, headers=hacker_headers)
    
    # Project endpoints typically return 404 or 403 for not-found/unauthorized
    assert res_loc.status_code in (403, 404)
