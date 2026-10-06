import pytest
import os
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import db_manager
from backend.auth import create_access_token
from backend.config import settings

@pytest.fixture(autouse=True)
def setup_teardown():
    original_db_path = getattr(db_manager, 'db_path', None)
    if hasattr(db_manager, 'db_path'):
        test_db_path = os.path.join(settings.STORAGE_DIR, "test_isolation_db.json")
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
        db_manager.db_path = test_db_path
        db_manager._data = {"users": [], "projects": [], "repositories": [], "indexes": []}
    
    yield
    
    if hasattr(db_manager, 'db_path') and os.path.exists(db_manager.db_path):
        os.remove(db_manager.db_path)
    if original_db_path:
        db_manager.db_path = original_db_path

@pytest.fixture
def client():
    return TestClient(app)

from backend.auth import create_access_token, User

def create_user_headers(user_id: str):
    user = User(id=user_id, username=user_id, email=f"{user_id}@test.com", role="user")
    token = create_access_token(user)
    db_manager.insert("users", {"id": user_id, "username": user_id, "hashed_password": "x", "email": f"{user_id}@test.com"})
    return {"Authorization": f"Bearer {token}"}

def test_project_ownership_isolation(client):
    headers_a = create_user_headers("user_a")
    headers_b = create_user_headers("user_b")
    
    # 1. User A creates Project A
    res = client.post("/api/projects", json={"name": "Project A"}, headers=headers_a)
    proj_a = res.json()["project_id"]
    
    # 2. User B creates Project B
    res = client.post("/api/projects", json={"name": "Project B"}, headers=headers_b)
    proj_b = res.json()["project_id"]
    
    # 3. User A tries to access Project B
    assert client.get(f"/api/projects/{proj_b}", headers=headers_a).status_code == 404
    
    # 4. User B tries to access Project A
    assert client.get(f"/api/projects/{proj_a}", headers=headers_b).status_code == 404
    
    # User A creates Repo A in Project A
    res = client.post(f"/api/projects/{proj_a}/repositories", json={"name": "Repo A", "source_path": "/a"}, headers=headers_a)
    repo_a = res.json()["repository_id"]
    
    # User B creates Repo B in Project B
    res = client.post(f"/api/projects/{proj_b}/repositories", json={"name": "Repo B", "source_path": "/b"}, headers=headers_b)
    repo_b = res.json()["repository_id"]
    
    # 5. User A tries to access Repo B
    assert client.get(f"/api/projects/{proj_b}/repositories/{repo_b}", headers=headers_a).status_code == 404
    
    # 6. User B tries to access Repo A
    assert client.get(f"/api/projects/{proj_a}/repositories/{repo_a}", headers=headers_b).status_code == 404
    
    # 7. Invalid combination (User A tries to access Repo B inside Project A)
    # Project A belongs to A, but Repo B does not belong to Project A
    assert client.get(f"/api/projects/{proj_a}/repositories/{repo_b}", headers=headers_a).status_code == 404

    # 8. User B tries to ingest Repo A
    assert client.post(f"/api/projects/{proj_a}/repositories/{repo_a}/ingest", json={}, headers=headers_b).status_code == 404
