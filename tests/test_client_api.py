import pytest
from unittest.mock import MagicMock, patch
import requests

from client.api import RemoteClient
from client.exceptions import (
    AuthenticationError,
    NotFoundError,
    ValidationError,
    ServerError,
    ConnectionError as ClientConnectionError,
)

@pytest.fixture
def mock_response():
    def _make_mock(status_code, json_data=None, text_data=""):
        mock = MagicMock(spec=requests.Response)
        mock.status_code = status_code
        if json_data is not None:
            mock.json.return_value = json_data
        else:
            mock.json.side_effect = ValueError("No JSON object could be decoded")
        mock.text = text_data
        return mock
    return _make_mock

@pytest.fixture
def client():
    return RemoteClient(base_url="http://fake-server", token="fake-token")

@patch("requests.Session.post")
def test_login_success(mock_post, mock_response):
    mock_post.return_value = mock_response(200, {"access_token": "new-token", "token_type": "bearer"})
    
    client = RemoteClient(base_url="http://fake-server")
    token = client.login("user", "pass")
    
    assert token == "new-token"
    assert client.token == "new-token"
    mock_post.assert_called_once()
    
@patch("requests.Session.request")
def test_get_me_success(mock_request, client, mock_response):
    mock_request.return_value = mock_response(200, {
        "id": "123", "username": "test", "email": "a@b.c", "role": "user"
    })
    
    user = client.get_me()
    assert user.id == "123"
    assert user.username == "test"

@patch("requests.Session.request")
def test_create_project(mock_request, client, mock_response):
    mock_request.return_value = mock_response(200, {
        "project_id": "p1", "name": "P1", "owner_user_id": "u1", "created_at": "100", "updated_at": "100", "status": "active"
    })
    proj = client.create_project("P1")
    assert proj.project_id == "p1"

@patch("requests.Session.request")
def test_list_projects(mock_request, client, mock_response):
    mock_request.return_value = mock_response(200, [
        {"project_id": "p1", "name": "P1", "owner_user_id": "u1", "created_at": "100", "updated_at": "100", "status": "active"}
    ])
    projs = client.list_projects()
    assert len(projs) == 1
    assert projs[0].project_id == "p1"

@patch("requests.Session.request")
def test_create_repository(mock_request, client, mock_response):
    mock_request.return_value = mock_response(200, {
        "repository_id": "r1", "project_id": "p1", "name": "R1", 
        "source_path": "/a", "storage_path": "/b", "current_version": "v1", "created_at": "100", "updated_at": "100", "status": "active"
    })
    repo = client.create_repository("p1", "R1", "/a")
    assert repo.repository_id == "r1"

@patch("requests.Session.request")
def test_list_repositories(mock_request, client, mock_response):
    mock_request.return_value = mock_response(200, [])
    repos = client.list_repositories("p1")
    assert repos == []

@patch("requests.Session.request")
def test_sync_manifest(mock_request, client, mock_response):
    mock_request.return_value = mock_response(200, {
        "need": ["a.py"], "delete": ["b.py"], "unchanged": 1
    })
    manifest = {"a.py": "hash"}
    res = client.sync_manifest("p1", "r1", manifest)
    assert res["need"] == ["a.py"]
    assert res["unchanged"] == 1

@patch("requests.Session.request")
def test_upload_files(mock_request, client, mock_response, tmp_path):
    mock_request.return_value = mock_response(200, {"uploaded": ["a.py"], "total_size": 10})
    (tmp_path / "a.py").write_text("hello")
    res = client.upload_files("p1", "r1", str(tmp_path), ["a.py"])
    assert res["uploaded"] == ["a.py"]

@patch("requests.Session.request")
def test_ingest_repository(mock_request, client, mock_response):
    mock_request.return_value = mock_response(200, {
        "index_id": "i1", "repository_id": "r1", "project_id": "p1",
        "index_path": "x", "graph_path": "y", "index_version": "v1",
        "repository_version": "v1", "embedding_model": "tfidf", 
        "chunking_version": "v1", "last_indexed_at": "100.0"
    })
    meta = client.ingest_repository("p1", "r1")
    assert meta.index_id == "i1"

@patch("requests.Session.request")
def test_ask(mock_request, client, mock_response):
    mock_request.return_value = mock_response(200, {
        "repo_id": "r1", "question": "q", "answer": "a", "intent": "general"
    })
    ans = client.ask("r1", "q", project_id="p1")
    assert ans.answer == "a"

@patch("requests.Session.request")
def test_auth_failure(mock_request, client, mock_response):
    mock_request.return_value = mock_response(401, {"detail": "Invalid creds"})
    with pytest.raises(AuthenticationError, match="Invalid creds"):
        client.get_me()

@patch("requests.Session.request")
def test_not_found(mock_request, client, mock_response):
    mock_request.return_value = mock_response(404, {"detail": "Not found"})
    with pytest.raises(NotFoundError, match="Not found"):
        client.get_project("missing")

@patch("requests.Session.request")
def test_server_error(mock_request, client, mock_response):
    mock_request.return_value = mock_response(500, {"detail": "Internal"})
    with pytest.raises(ServerError, match="Internal"):
        client.get_me()

@patch("requests.Session.request")
def test_validation_error(mock_request, client, mock_response):
    mock_request.return_value = mock_response(422, {"detail": "Bad body"})
    with pytest.raises(ValidationError, match="Bad body"):
        client.get_me()

@patch("requests.Session.request")
def test_connection_error(mock_request, client):
    mock_request.side_effect = requests.exceptions.ConnectionError("Network down")
    with pytest.raises(ClientConnectionError, match="Failed to connect"):
        client.get_me()

def test_token_not_in_error_message(mock_response):
    client = RemoteClient(base_url="http://fake", token="SUPER_SECRET_TOKEN")
    with patch("requests.Session.request") as mock_request:
        mock_request.return_value = mock_response(401, {"detail": "Invalid auth"})
        try:
            client.get_me()
        except AuthenticationError as e:
            msg = str(e)
            assert "SUPER_SECRET_TOKEN" not in msg

    with patch("requests.Session.request") as mock_request:
        mock_request.side_effect = requests.exceptions.ConnectionError("Timeout")
        try:
            client.get_me()
        except ClientConnectionError as e:
            msg = str(e)
            assert "SUPER_SECRET_TOKEN" not in msg

@patch("requests.Session.request")
def test_auth_header_included(mock_request, mock_response):
    client = RemoteClient(base_url="http://fake", token="MYTOKEN")
    mock_request.return_value = mock_response(200, [])
    client.list_projects()
    
    mock_request.assert_called_once()
    headers = mock_request.call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer MYTOKEN"
