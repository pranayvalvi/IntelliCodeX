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

import base64

def test_sync_upload_basic(sync_client, auth_headers, tmp_path):
    res_proj = sync_client.post("/api/projects", json={"name": "Upload Proj"}, headers=auth_headers)
    project_id = res_proj.json()["project_id"]
    res_repo = sync_client.post(f"/api/projects/{project_id}/repositories", json={"name": "Upload Repo", "source_path": "/x"}, headers=auth_headers)
    repo_id = res_repo.json()["repository_id"]
    
    b64_a = base64.b64encode(b"hello a").decode("utf-8")
    b64_b = base64.b64encode(b"hello b").decode("utf-8")
    
    payload = {
        "files": [
            {"path": "a.py", "content": b64_a},
            {"path": "b.py", "content": b64_b}
        ]
    }
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/upload", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "a.py" in data["uploaded"]
    assert "b.py" in data["uploaded"]
    assert data["total_size"] == 14

def test_sync_upload_security(sync_client, auth_headers, tmp_path):
    res_proj = sync_client.post("/api/projects", json={"name": "Sec Upload Proj"}, headers=auth_headers)
    project_id = res_proj.json()["project_id"]
    res_repo = sync_client.post(f"/api/projects/{project_id}/repositories", json={"name": "Sec Upload Repo", "source_path": "/x"}, headers=auth_headers)
    repo_id = res_repo.json()["repository_id"]
    
    b64_bad = base64.b64encode(b"bad").decode("utf-8")
    
    # 7. Path traversal
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/upload", json={"files": [{"path": "../passwd", "content": b64_bad}]}, headers=auth_headers)
    assert res.status_code == 400
        
    # 8. Absolute path
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/upload", json={"files": [{"path": "/etc/passwd", "content": b64_bad}]}, headers=auth_headers)
    assert res.status_code == 400
        
    # 9. Windows path
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/upload", json={"files": [{"path": "C:/Windows", "content": b64_bad}]}, headers=auth_headers)
    assert res.status_code == 400

    # 10. Null bytes
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/upload", json={"files": [{"path": "test\0.py", "content": b64_bad}]}, headers=auth_headers)
    assert res.status_code == 400

def test_sync_upload_auth(sync_client, auth_headers):
    # 1, 2, 3
    res_proj = sync_client.post("/api/projects", json={"name": "Auth Proj"}, headers=auth_headers)
    project_id = res_proj.json()["project_id"]
    res_repo = sync_client.post(f"/api/projects/{project_id}/repositories", json={"name": "Auth Repo", "source_path": "/x"}, headers=auth_headers)
    repo_id = res_repo.json()["repository_id"]
    
    # Missing auth
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/upload", json={"files": []})
    assert res.status_code in [401, 403]
    
    # Wrong owner
    res_b = sync_client.post("/api/auth/register", json={"username": "userc", "email": "c@test.com", "password": "password"})
    res_b = sync_client.post("/api/auth/login", json={"username": "userc", "password": "password"})
    auth_b = {"Authorization": f"Bearer {res_b.json()['access_token']}"}
    
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/upload", json={"files": []}, headers=auth_b)
    assert res.status_code == 403
import base64
from unittest.mock import patch

def test_sync_index_basic(sync_client, auth_headers, tmp_path):
    res_proj = sync_client.post("/api/projects", json={"name": "Idx Proj"}, headers=auth_headers)
    project_id = res_proj.json()["project_id"]
    res_repo = sync_client.post(f"/api/projects/{project_id}/repositories", json={"name": "Idx Repo", "source_path": "/x"}, headers=auth_headers)
    repo_id = res_repo.json()["repository_id"]
    
    # 1. Initial indexing
    # First upload some files
    b64_a = base64.b64encode(b"def a(): pass").decode("utf-8")
    b64_b = base64.b64encode(b"def b(): pass").decode("utf-8")
    
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/upload", json={
        "files": [{"path": "a.py", "content": b64_a}, {"path": "b.py", "content": b64_b}]
    }, headers=auth_headers)
    assert res.status_code == 200
    
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/index", json={"backend": "tfidf"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert data["files_added"] == 2
    assert data["files_modified"] == 0
    assert data["files_deleted"] == 0
    assert data["files_unchanged"] == 0
    assert data["index_updated"] == True
    assert data["chunks_indexed"] > 0
    
    # 2. Unchanged files are not unnecessarily reprocessed (No changes)
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/index", json={"backend": "tfidf"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["files_added"] == 0
    assert data["files_modified"] == 0
    assert data["files_deleted"] == 0
    assert data["files_unchanged"] == 2
    assert data["index_updated"] == False
    
    # 3. One modified file
    b64_a2 = base64.b64encode(b"def a(): print('hi')").decode("utf-8")
    sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/upload", json={
        "files": [{"path": "a.py", "content": b64_a2}]
    }, headers=auth_headers)
    
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/index", json={"backend": "tfidf"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["files_added"] == 0
    assert data["files_modified"] == 1
    assert data["files_unchanged"] == 1
    assert data["index_updated"] == True
    
    # 4. One new file
    b64_c = base64.b64encode(b"def c(): pass").decode("utf-8")
    sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/upload", json={
        "files": [{"path": "c.py", "content": b64_c}]
    }, headers=auth_headers)
    
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/index", json={"backend": "tfidf"}, headers=auth_headers)
    data = res.json()
    assert data["files_added"] == 1
    assert data["files_modified"] == 0
    assert data["files_unchanged"] == 2
    assert data["index_updated"] == True
    
    # 5. One deleted file
    # We can delete a file from the server storage manually to simulate sync deletion,
    # or rely on the manifest delta. Wait, our `sync_upload` currently doesn't delete files.
    # The `detect_repository_changes` compares the filesystem with the SQLite DB.
    # We need a delete endpoint, or we just use os.remove directly in the test to simulate it.
    user_res = sync_client.get("/api/auth/me", headers=auth_headers)
    user_id = user_res.json()["id"]
    from core.persistence import get_repo_id
    internal_repo_id = get_repo_id(res_repo.json()["storage_path"])
    
    import os
    server_c_path = os.path.join(".storage", "projects", user_id, project_id, "repository", internal_repo_id, "c.py")
    if os.path.exists(server_c_path):
        os.remove(server_c_path)
        
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/index", json={"backend": "tfidf"}, headers=auth_headers)
    data = res.json()
    assert data["files_deleted"] == 1
    assert data["files_unchanged"] == 2
    assert data["index_updated"] == True

@patch("core.pipeline.chunk_repository")
def test_sync_index_performance(mock_chunk_repository, sync_client, auth_headers):
    # Just a mock wrapper to count calls
    def side_effect(files):
        from core.chunker import CodeChunk
        return [CodeChunk(chunk_id="f_0.py::func_0", file_path="f_0.py", code="dummy", language="python", start_line=1, end_line=1, kind="function", name="func_0")]
        
    mock_chunk_repository.side_effect = side_effect

    res_proj = sync_client.post("/api/projects", json={"name": "Perf Proj"}, headers=auth_headers)
    project_id = res_proj.json()["project_id"]
    res_repo = sync_client.post(f"/api/projects/{project_id}/repositories", json={"name": "Perf Repo", "source_path": "/x"}, headers=auth_headers)
    repo_id = res_repo.json()["repository_id"]
    
    # Upload 100 files
    files = []
    for i in range(100):
        b64_content = base64.b64encode(f"def func_{i}(): pass".encode("utf-8")).decode("utf-8")
        files.append({"path": f"f_{i}.py", "content": b64_content})
        
    sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/upload", json={"files": files}, headers=auth_headers)
    
    # 1. Initial index
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/index", json={"backend": "tfidf"}, headers=auth_headers)
    assert res.status_code == 200
    
    mock_chunk_repository.reset_mock()
    
    # Modify 1 file
    b64_mod = base64.b64encode(b"def func_0(): print('changed')").decode("utf-8")
    sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/upload", json={"files": [{"path": "f_0.py", "content": b64_mod}]}, headers=auth_headers)
    
    # 2. Incremental index
    res = sync_client.post(f"/api/projects/{project_id}/repositories/{repo_id}/sync/index", json={"backend": "tfidf"}, headers=auth_headers)
    assert res.status_code == 200
    
    # Verify chunk_repository was called with EXACTLY 1 file, not 100.
    mock_chunk_repository.assert_called_once()
    called_files = mock_chunk_repository.call_args[0][0]
    assert len(called_files) == 1
    assert called_files[0].rel_path == "f_0.py"
