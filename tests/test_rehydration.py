import pytest
import os
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import db_manager
from backend.auth import create_access_token, User
from backend.config import settings

@pytest.fixture(autouse=True)
def setup_teardown():
    original_db_path = getattr(db_manager, 'db_path', None)
    if hasattr(db_manager, 'db_path'):
        test_db_path = os.path.join(settings.STORAGE_DIR, "test_rehydrate_db.json")
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
        db_manager.db_path = test_db_path
        db_manager._data = {"users": [], "projects": [], "repositories": [], "indexes": []}
    
    from backend.api.repos import ACTIVE_REPOS
    ACTIVE_REPOS.clear()
    
    yield
    
    if hasattr(db_manager, 'db_path') and os.path.exists(db_manager.db_path):
        os.remove(db_manager.db_path)
    if original_db_path:
        db_manager.db_path = original_db_path

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_headers():
    user = User(id="testuser_rehyd", username="testuser_rehyd", email="test@test.com", role="user")
    token = create_access_token(user)
    db_manager.insert("users", {"id": "testuser_rehyd", "username": "testuser_rehyd", "hashed_password": "x", "email": "test@test.com"})
    return {"Authorization": f"Bearer {token}"}

def test_rehydration_flow(client, auth_headers, tmp_path):
    # 1. Create a dummy repository directory
    dummy_repo_path = str(tmp_path / "dummy_rehyd_repo")
    os.makedirs(dummy_repo_path, exist_ok=True)
    with open(os.path.join(dummy_repo_path, "main.py"), "w") as f:
        f.write("def calculate_sum(a, b):\n    return a + b\n")
        
    # 2. Create a project and repo
    res_proj = client.post("/api/projects", json={"name": "Test Project"}, headers=auth_headers)
    project_id = res_proj.json()["project_id"]
    
    res_repo = client.post(
        f"/api/projects/{project_id}/repositories",
        json={"name": "Test Repo", "source_path": dummy_repo_path},
        headers=auth_headers
    )
    repository_id = res_repo.json()["repository_id"]
    
    # 3. Ingest repository (this adds to ACTIVE_REPOS initially)
    res_ingest = client.post(
        f"/api/projects/{project_id}/repositories/{repository_id}/ingest",
        json={"backend": "tfidf", "force_reindex": True},
        headers=auth_headers
    )
    assert res_ingest.status_code == 200
    
    # 4. Clear ACTIVE_REPOS to simulate restart
    from backend.api.repos import ACTIVE_REPOS
    ACTIVE_REPOS.clear()
    assert repository_id not in ACTIVE_REPOS
    
    # 5. Query chat API (should trigger rehydration)
    res_chat = client.post(
        "/api/chat/ask",
        json={"repo_id": repository_id, "project_id": project_id, "question": "What does calculate_sum do?"},
        headers=auth_headers
    )
    assert res_chat.status_code == 200
    
    # Verify it rehydrated the cache
    assert repository_id in ACTIVE_REPOS
    assert ACTIVE_REPOS[repository_id]["meta"]["project_id"] == project_id
    
    ACTIVE_REPOS.clear()
    
    # 6. Query bugs API (should trigger rehydration)
    res_bugs = client.post(
        "/api/bugs/localize",
        json={"repo_id": repository_id, "project_id": project_id, "error_report": "Error in calculate_sum"},
        headers=auth_headers
    )
    assert res_bugs.status_code == 200
    
    ACTIVE_REPOS.clear()
    
    # 7. Query patch API (should trigger rehydration)
    res_patch = client.post(
        "/api/patches/generate",
        json={"repo_id": repository_id, "project_id": project_id, "error_report": "Fix calculate_sum bug"},
        headers=auth_headers
    )
    assert res_patch.status_code == 200
def test_rehydration_isolation(client, auth_headers, tmp_path):
    # 1. User B tries to query User A's repo (repository_id exists but belongs to A)
    # First create A's project
    dummy_repo_path = str(tmp_path / "dummy_rehyd_repo2")
    os.makedirs(dummy_repo_path, exist_ok=True)
    with open(os.path.join(dummy_repo_path, "main.py"), "w") as f:
        f.write("def calculate_sum(a, b):\n    return a + b\n")
    
    res_proj = client.post("/api/projects", json={"name": "Project A"}, headers=auth_headers)
    project_id = res_proj.json()["project_id"]
    
    res_repo = client.post(
        f"/api/projects/{project_id}/repositories",
        json={"name": "Repo A", "source_path": dummy_repo_path},
        headers=auth_headers
    )
    repository_id = res_repo.json()["repository_id"]
    
    res_ingest = client.post(
        f"/api/projects/{project_id}/repositories/{repository_id}/ingest",
        json={"backend": "tfidf", "force_reindex": True},
        headers=auth_headers
    )
    
    # Create User B
    user_b = User(id="user_b", username="user_b", email="b@test.com", role="user")
    token_b = create_access_token(user_b)
    db_manager.insert("users", {"id": "user_b", "username": "user_b", "hashed_password": "x", "email": "b@test.com"})
    headers_b = {"Authorization": f"Bearer {token_b}"}
    
    from backend.api.repos import ACTIVE_REPOS
    ACTIVE_REPOS.clear()
    
    # User B attempts to access Repo A via chat
    res_chat = client.post(
        "/api/chat/ask",
        json={"repo_id": repository_id, "project_id": project_id, "question": "What does calculate_sum do?"},
        headers=headers_b
    )
    assert res_chat.status_code == 403
