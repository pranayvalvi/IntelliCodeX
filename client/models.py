from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class User(BaseModel):
    id: str
    username: str
    email: str
    role: str

class Project(BaseModel):
    project_id: str
    name: str
    owner_user_id: str
    created_at: str
    updated_at: str
    status: str

class Repository(BaseModel):
    repository_id: str
    project_id: str
    name: str
    source_path: str
    storage_path: str
    current_version: str
    created_at: str
    updated_at: str
    status: str

class IndexMetadata(BaseModel):
    index_id: str
    repository_id: str
    project_id: str
    index_path: str
    graph_path: str
    index_version: str
    repository_version: str
    embedding_model: str
    chunking_version: str
    last_indexed_at: str

class ChatResponse(BaseModel):
    repo_id: str
    question: str
    answer: str
    intent: str
    retrieved_chunks: List[Dict[str, Any]] = []
    relevant_files: List[str] = []
    functions: List[str] = []
    code_snippets: List[str] = []
    dependency_relationships: List[str] = []
