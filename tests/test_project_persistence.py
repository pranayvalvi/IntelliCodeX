import pytest
import os
import shutil
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import db_manager
from backend.auth import create_access_token
from backend.config import settings

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup: Use a clean test DB file for local disk store
    original_db_path = getattr(db_manager, 'db_path', None)
    if hasattr(db_manager, 'db_path'):
        test_db_path = os.path.join(settings.STORAGE_DIR, "test_db.json")
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
        db_manager.db_path = test_db_path
        db_manager._data = {"users": [], "projects": [], "repositories": [], "indexes": []}
    
    yield
    
    # Teardown
    if hasattr(db_manager, 'db_path'):
        if os.path.exists(db_manager.db_path):
            os.remove(db_manager.db_path)
        db_manager.db_path = original_db_path

@pytest.fixture
def client():
    return TestClient(app)

from backend.auth import create_access_token, User

@pytest.fixture
def auth_headers():
    user = User(id="testuser", username="testuser", email="test@test.com", role="user")
    token = create_access_token(user)
    db_manager.insert("users", {"id": "testuser", "username": "testuser", "hashed_password": "x", "email": "test@test.com"})
    return {"Authorization": f"Bearer {token}"}

def test_project_persistence_flow(client, auth_headers, tmp_path):
    # 1. Create a dummy repository directory
    dummy_repo_path = str(tmp_path / "dummy_repo")
    os.makedirs(dummy_repo_path, exist_ok=True)
    with open(os.path.join(dummy_repo_path, "main.py"), "w") as f:
        f.write("def hello(): pass")
        
    # 2. Create a project
    res_proj = client.post("/api/projects", json={"name": "Test Project"}, headers=auth_headers)
    assert res_proj.status_code == 200
    proj = res_proj.json()
    project_id = proj["project_id"]
    
    # 3. Create a repository
    res_repo = client.post(
        f"/api/projects/{project_id}/repositories",
        json={"name": "Test Repo", "source_path": dummy_repo_path},
        headers=auth_headers
    )
    assert res_repo.status_code == 200
    repo = res_repo.json()
    repository_id = repo["repository_id"]
    
    # 4. Ingest repository via new API
    res_ingest = client.post(
        f"/api/projects/{project_id}/repositories/{repository_id}/ingest",
        json={"backend": "tfidf", "force_reindex": True},
        headers=auth_headers
    )
    assert res_ingest.status_code == 200
    idx = res_ingest.json()
    assert idx["embedding_model"] == "tfidf"
    assert "indexes" in idx["index_path"]
    
    # 5. Verify index files are stored under the correct project directory
    assert os.path.exists(idx["index_path"])
    
    # 6. Simulate restart (reload from disk if using LocalDiskStore)
    if hasattr(db_manager, '_load'):
        db_manager._data = {}
        db_manager._load()
        
    # 7. Retrieve project
    res_proj_get = client.get(f"/api/projects/{project_id}", headers=auth_headers)
    assert res_proj_get.status_code == 200
    
    # 8. Retrieve repo
    res_repo_get = client.get(f"/api/projects/{project_id}/repositories/{repository_id}", headers=auth_headers)
    assert res_repo_get.status_code == 200
    
    # 9. Retrieve index metadata
    res_idx_get = client.get(f"/api/projects/{project_id}/repositories/{repository_id}/indexes", headers=auth_headers)
    assert res_idx_get.status_code == 200
    assert len(res_idx_get.json()) == 1
    assert res_idx_get.json()[0]["embedding_model"] == "tfidf"
