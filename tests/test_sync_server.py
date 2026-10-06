import pytest
import os
import sqlite3
from backend.main import app
from fastapi.testclient import TestClient
from core.persistence import get_db_connection, init_schema

@pytest.fixture
def sync_client():
    return TestClient(app)

@pytest.fixture
def auth_headers(sync_client):
    res = sync_client.post("/api/auth/register", json={"username": "syncuser", "email": "sync@test.com", "password": "password"})
    res = sync_client.post("/api/auth/login", json={"username": "syncuser", "password": "password"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}

def test_sync_manifest_basic(sync_client, auth_headers):
    # Create project and repo
    res_proj = sync_client.post("/api/projects", json={"name": "Sync Project"}, headers=auth_headers)
    assert res_proj.status_code == 200, res_proj.text
    project_id = res_proj.json()["project_id"]
    
    res_repo = sync_client.post(f"/api/projects/{project_id}/repositories", json={"name": "Sync Repo", "source_path": "/fake/path"}, headers=auth_headers)
    assert res_repo.status_code == 200, res_repo.text
    repo_id = res_repo.json()["repository_id"]

    # 1. Empty manifest
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/manifest", json={"files": {}}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["need"] == []
    assert data["delete"] == []
    assert data["unchanged"] == 0

    # 2. New files returned in need
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/manifest", json={"files": {"main.py": "hash123"}}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "main.py" in data["need"]

    # 3, 4, 5. To test unchanged/modified/deleted, we need to mock or inject the server DB.
    # The server reads from .storage/projects/<user>/<project>/metadata/metadata.db
    # Let's seed the db.
    user_res = sync_client.get("/api/auth/me", headers=auth_headers)
    user_id = user_res.json()["id"]
    
    storage_path = res_repo.json()["storage_path"]
    from core.persistence import get_repo_id
    internal_repo_id = get_repo_id(storage_path)
    
    db_dir = os.path.join(".storage", "projects", user_id, project_id, "metadata")
    os.makedirs(db_dir, exist_ok=True)
    conn = get_db_connection(os.path.join(db_dir, "metadata.db"))
    init_schema(conn)
    # Insert some mock files: a.py, b.py, c.py
    import time
    conn.execute("INSERT INTO repos (repo_id, repo_path, backend, last_indexed_at) VALUES (?, ?, ?, ?)", (internal_repo_id, storage_path, "tfidf", time.time()))
    conn.execute("INSERT INTO files (repo_id, rel_path, file_hash, mtime, language) VALUES (?, ?, ?, ?, ?)", (internal_repo_id, "a.py", "hash_a", time.time(), "python"))
    conn.execute("INSERT INTO files (repo_id, rel_path, file_hash, mtime, language) VALUES (?, ?, ?, ?, ?)", (internal_repo_id, "b.py", "hash_b", time.time(), "python"))
    conn.execute("INSERT INTO files (repo_id, rel_path, file_hash, mtime, language) VALUES (?, ?, ?, ?, ?)", (internal_repo_id, "c.py", "hash_c", time.time(), "python"))
    conn.commit()
    conn.close()
    
    # Test changes
    manifest = {
        "a.py": "hash_a",       # Unchanged
        "b.py": "hash_b_new",   # Modified -> Need
        "d.py": "hash_d"        # New -> Need
        # "c.py" is missing -> Delete
    }
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/manifest", json={"files": manifest}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    
    assert "b.py" in data["need"]
    assert "d.py" in data["need"]
    assert "a.py" not in data["need"]
    
    assert "c.py" in data["delete"]
    
    assert data["unchanged"] == 1

def test_sync_manifest_security(sync_client, auth_headers):
    # Setup
    res_proj = sync_client.post("/api/projects", json={"name": "Sec Project"}, headers=auth_headers)
    project_id = res_proj.json()["project_id"]
    res_repo = sync_client.post(f"/api/projects/{project_id}/repositories", json={"name": "Sec Repo", "source_path": "/fake/path"}, headers=auth_headers)
    repo_id = res_repo.json()["repository_id"]

    # 6. Path traversal rejected
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/manifest", json={"files": {"../etc/passwd": "hash"}}, headers=auth_headers)
    assert res.status_code == 400

    # 7. Absolute paths rejected
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/manifest", json={"files": {"/absolute/path": "hash"}}, headers=auth_headers)
    assert res.status_code == 400

    # Windows drive paths
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/manifest", json={"files": {"C:/Windows/path": "hash"}}, headers=auth_headers)
    assert res.status_code == 400
    
    # Null bytes
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/manifest", json={"files": {"test\0.py": "hash"}}, headers=auth_headers)
    assert res.status_code == 400

    # 9. Authentication required
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/manifest", json={"files": {}})
    assert res.status_code in [401, 403]

def test_sync_manifest_cross_project(sync_client, auth_headers):
    # User A setup
    res_proj_a = sync_client.post("/api/projects", json={"name": "Proj A"}, headers=auth_headers)
    project_id_a = res_proj_a.json()["project_id"]
    res_repo_a = sync_client.post(f"/api/projects/{project_id_a}/repositories", json={"name": "Repo A", "source_path": "/a"}, headers=auth_headers)
    repo_id_a = res_repo_a.json()["repository_id"]

    # User B setup
    res = sync_client.post("/api/auth/register", json={"username": "userb", "email": "b@test.com", "password": "password"})
    res = sync_client.post("/api/auth/login", json={"username": "userb", "password": "password"})
    auth_b = {"Authorization": f"Bearer {res.json()['access_token']}"}
    
    res_proj_b = sync_client.post("/api/projects", json={"name": "Proj B"}, headers=auth_b)
    project_id_b = res_proj_b.json()["project_id"]

    # 8. Cross-project repository access rejected
    # User B trying to access User A's project
    res = sync_client.post(f"/api/projects/{project_id_a}/repositories/{repo_id_a}/sync/manifest", json={"files": {}}, headers=auth_b)
    assert res.status_code == 403

    # User A trying to use Repo A inside Proj B
    res = sync_client.post(f"/api/projects/{project_id_b}/repositories/{repo_id_a}/sync/manifest", json={"files": {}}, headers=auth_headers)
    assert res.status_code == 403
    # User A is not owner of Proj B -> 403
