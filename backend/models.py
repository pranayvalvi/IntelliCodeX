from typing import Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import uuid

def utc_now_str() -> str:
    return datetime.now(timezone.utc).isoformat()

def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

class ProjectBase(BaseModel):
    name: str

class ProjectCreate(ProjectBase):
    pass

class Project(ProjectBase):
    project_id: str
    owner_user_id: str
    created_at: str = Field(default_factory=utc_now_str)
    updated_at: str = Field(default_factory=utc_now_str)
    status: str = "active"

class RepositoryBase(BaseModel):
    name: str
    source_path: str  # Client's local path metadata

class RepositoryCreate(RepositoryBase):
    pass

class Repository(RepositoryBase):
    repository_id: str
    project_id: str
    storage_path: str
    current_version: str = "v1"
    created_at: str = Field(default_factory=utc_now_str)
    updated_at: str = Field(default_factory=utc_now_str)
    status: str = "active"

class IndexMetadataBase(BaseModel):
    index_version: str = "v1"
    repository_version: str = "v1"
    embedding_model: str
    chunking_version: str = "v1"

class IndexMetadataCreate(IndexMetadataBase):
    pass

class IndexMetadata(IndexMetadataBase):
    index_id: str
    repository_id: str
    project_id: str
    index_path: str
    graph_path: str
    last_indexed_at: str = Field(default_factory=utc_now_str)
