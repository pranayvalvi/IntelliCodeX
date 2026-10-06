import os
import requests
from typing import List, Optional, Dict, Any

from client.exceptions import (
    RemoteAPIError,
    AuthenticationError,
    NotFoundError,
    ValidationError,
    ServerError,
    ConnectionError as ClientConnectionError,
)
from client.models import User, Project, Repository, IndexMetadata, ChatResponse


class RemoteClient:
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None, timeout: int = 30):
        """
        Initializes the RemoteClient.
        Reads INTELLICODEX_SERVER_URL from environment if base_url is not provided.
        """
        self.base_url = (base_url or os.environ.get("INTELLICODEX_SERVER_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.token = token
        self.timeout = timeout
        self.session = requests.Session()

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _handle_response(self, response: requests.Response) -> Any:
        if 200 <= response.status_code < 300:
            try:
                return response.json()
            except ValueError:
                return response.text
                
        error_detail = "Unknown error"
        try:
            error_json = response.json()
            error_detail = error_json.get("detail", error_detail)
        except ValueError:
            error_detail = response.text

        if response.status_code in (401, 403):
            raise AuthenticationError(f"Authentication failed ({response.status_code}): {error_detail}")
        elif response.status_code == 404:
            raise NotFoundError(f"Resource not found: {error_detail}")
        elif response.status_code in (400, 422):
            raise ValidationError(f"Validation error ({response.status_code}): {error_detail}")
        elif response.status_code >= 500:
            raise ServerError(f"Server error ({response.status_code}): {error_detail}")
        else:
            raise RemoteAPIError(f"API Error ({response.status_code}): {error_detail}")

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                timeout=self.timeout,
                **kwargs
            )
            return self._handle_response(resp)
        except requests.exceptions.ConnectionError as e:
            raise ClientConnectionError(f"Failed to connect to {self.base_url}") from e
        except requests.exceptions.Timeout as e:
            raise ClientConnectionError(f"Request to {self.base_url} timed out") from e
        except requests.exceptions.RequestException as e:
            raise RemoteAPIError(f"Request failed: {str(e)}") from e

    # --- Authentication ---
    
    def login(self, username: str, password: str) -> str:
        """Authenticates and sets the token. Returns the token."""
        data = {"username": username, "password": password}
        try:
            resp = self.session.post(
                f"{self.base_url}/api/auth/login",
                json=data,
                timeout=self.timeout
            )
            result = self._handle_response(resp)
            self.token = result.get("access_token")
            return self.token
        except requests.exceptions.ConnectionError as e:
            raise ClientConnectionError(f"Failed to connect to {self.base_url}") from e

    def get_me(self) -> User:
        """Returns the currently authenticated user."""
        result = self._request("GET", "/api/auth/me")
        return User(**result)

    # --- Projects ---

    def create_project(self, name: str) -> Project:
        payload = {"name": name}
        result = self._request("POST", "/api/projects", json=payload)
        return Project(**result)

    def list_projects(self) -> List[Project]:
        result = self._request("GET", "/api/projects")
        return [Project(**p) for p in result]

    def get_project(self, project_id: str) -> Project:
        result = self._request("GET", f"/api/projects/{project_id}")
        return Project(**result)

    # --- Repositories ---

    def create_repository(self, project_id: str, name: str, source_path: str) -> Repository:
        payload = {"name": name, "source_path": source_path}
        result = self._request("POST", f"/api/projects/{project_id}/repositories", json=payload)
        return Repository(**result)

    def list_repositories(self, project_id: str) -> List[Repository]:
        result = self._request("GET", f"/api/projects/{project_id}/repositories")
        return [Repository(**r) for r in result]

    def get_repository(self, project_id: str, repository_id: str) -> Repository:
        result = self._request("GET", f"/api/projects/{project_id}/repositories/{repository_id}")
        return Repository(**result)

    # --- Sync ---
    
    def sync_manifest(self, project_id: str, repository_id: str, manifest: Dict[str, str]) -> Dict[str, Any]:
        """
        Sends a manifest of client files (relative_path -> sha256) to the server.
        Returns a dictionary with 'need', 'delete', and 'unchanged' keys.
        """
        payload = {"files": manifest}
        result = self._request("POST", f"/api/projects/{project_id}/repositories/{repository_id}/sync/manifest", json=payload)
        return result

    def upload_files(self, project_id: str, repository_id: str, local_repo_path: str, files_to_upload: List[str]) -> Dict[str, Any]:
        """
        Uploads local files to the server using JSON and base64 encoding.
        """
        import base64
        if not files_to_upload:
            return {"uploaded": [], "total_size": 0}
            
        url = f"/api/projects/{project_id}/repositories/{repository_id}/sync/upload"
        
        file_payloads = []
        for rel_path in files_to_upload:
            abs_path = os.path.join(local_repo_path, rel_path)
            try:
                with open(abs_path, "rb") as f:
                    content_bytes = f.read()
                    b64_content = base64.b64encode(content_bytes).decode("utf-8")
                    file_payloads.append({"path": rel_path, "content": b64_content})
            except (OSError, IOError):
                pass
                
        payload = {"files": file_payloads}
        return self._request("POST", url, json=payload)

    def sync_index(self, project_id: str, repository_id: str, backend: str = "tfidf") -> Dict[str, Any]:
        """
        Triggers an incremental re-index of the repository on the server.
        """
        url = f"/api/projects/{project_id}/repositories/{repository_id}/sync/index"
        payload = {"backend": backend}
        return self._request("POST", url, json=payload)

    # --- Ingestion ---

    def ingest_repository(self, project_id: str, repository_id: str, backend: str = "tfidf", force_reindex: bool = False) -> IndexMetadata:
        payload = {"backend": backend, "force_reindex": force_reindex}
        result = self._request("POST", f"/api/projects/{project_id}/repositories/{repository_id}/ingest", json=payload)
        return IndexMetadata(**result)

    # --- Chat ---

    def ask(self, repository_id: str, question: str, project_id: Optional[str] = None, top_k: int = 5) -> ChatResponse:
        payload = {
            "repo_id": repository_id,
            "question": question,
            "top_k": top_k
        }
        if project_id:
            payload["project_id"] = project_id
            
        result = self._request("POST", "/api/chat/ask", json=payload)
        return ChatResponse(**result)

    # --- Repair / Bugs ---
    
    def localize_bug(self, project_id: str, repository_id: str, error_report: str, top_k: int = 5) -> Dict[str, Any]:
        url = "/api/bugs/localize"
        payload = {
            "project_id": project_id,
            "repo_id": repository_id,
            "error_report": error_report,
            "top_k": top_k
        }
        return self._request("POST", url, json=payload)

    def generate_patch(self, project_id: str, repository_id: str, error_report: str, target_file: Optional[str] = None, verify_in_sandbox: bool = False) -> Dict[str, Any]:
        url = "/api/patches/generate"
        payload = {
            "project_id": project_id,
            "repo_id": repository_id,
            "error_report": error_report,
            "verify_in_sandbox": verify_in_sandbox
        }
        if target_file:
            payload["target_file"] = target_file
        return self._request("POST", url, json=payload)
