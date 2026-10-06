from fastapi import APIRouter, HTTPException, Depends
from typing import List
import os

from backend.auth import User, get_current_user
from backend.database import db_manager
from backend.models import (
    Project, ProjectCreate, Repository, RepositoryCreate, 
    IndexMetadata, IndexMetadataCreate, generate_id, utc_now_str,
    SyncManifestRequest, SyncManifestResponse
)
from backend.config import settings

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.post("", response_model=Project)
def create_project(req: ProjectCreate, current_user: User = Depends(get_current_user)):
    project_id = generate_id("proj")
    project = Project(
        project_id=project_id,
        owner_user_id=current_user.id,
        name=req.name
    )
    db_manager.insert("projects", project.model_dump())
    return project

@router.get("", response_model=List[Project])
def list_projects(current_user: User = Depends(get_current_user)):
    docs = db_manager.find("projects", {"owner_user_id": current_user.id})
    return [Project(**doc) for doc in docs]

@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str, current_user: User = Depends(get_current_user)):
    doc = db_manager.find_one("projects", {"project_id": project_id, "owner_user_id": current_user.id})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    return Project(**doc)

@router.post("/{project_id}/repositories", response_model=Repository)
def create_repository(project_id: str, req: RepositoryCreate, current_user: User = Depends(get_current_user)):
    # Verify project ownership
    proj = db_manager.find_one("projects", {"project_id": project_id, "owner_user_id": current_user.id})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    repo_id = generate_id("repo")
    
    # Updated storage layout per phase 1 requirements
    # .storage/projects/<user_id>/<project_id>/repository/
    base_storage_path = os.path.join(settings.STORAGE_DIR, "projects", current_user.id, project_id)
    repo_storage_path = os.path.join(base_storage_path, "repository")
    index_storage_path = os.path.join(base_storage_path, "indexes")
    graphs_storage_path = os.path.join(base_storage_path, "graphs")
    meta_storage_path = os.path.join(base_storage_path, "metadata")
    
    os.makedirs(repo_storage_path, exist_ok=True)
    os.makedirs(index_storage_path, exist_ok=True)
    os.makedirs(graphs_storage_path, exist_ok=True)
    os.makedirs(meta_storage_path, exist_ok=True)
    
    repo = Repository(
        repository_id=repo_id,
        project_id=project_id,
        name=req.name,
        source_path=req.source_path,
        storage_path=base_storage_path
    )
    db_manager.insert("repositories", repo.model_dump())
    return repo

@router.get("/{project_id}/repositories", response_model=List[Repository])
def list_repositories(project_id: str, current_user: User = Depends(get_current_user)):
    proj = db_manager.find_one("projects", {"project_id": project_id, "owner_user_id": current_user.id})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    docs = db_manager.find("repositories", {"project_id": project_id})
    return [Repository(**doc) for doc in docs]

@router.get("/{project_id}/repositories/{repository_id}", response_model=Repository)
def get_repository(project_id: str, repository_id: str, current_user: User = Depends(get_current_user)):
    proj = db_manager.find_one("projects", {"project_id": project_id, "owner_user_id": current_user.id})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    doc = db_manager.find_one("repositories", {"repository_id": repository_id, "project_id": project_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Repository not found")
    return Repository(**doc)

@router.post("/{project_id}/repositories/{repository_id}/indexes", response_model=IndexMetadata)
def create_index_metadata(project_id: str, repository_id: str, req: IndexMetadataCreate, current_user: User = Depends(get_current_user)):
    # Verify project ownership
    proj = db_manager.find_one("projects", {"project_id": project_id, "owner_user_id": current_user.id})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # Verify repo belongs to this project
    repo_doc = db_manager.find_one("repositories", {"repository_id": repository_id, "project_id": project_id})
    if not repo_doc:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    index_id = generate_id("idx")
    base_storage_path = os.path.join(settings.STORAGE_DIR, "projects", current_user.id, project_id)
    
    meta = IndexMetadata(
        index_id=index_id,
        repository_id=repository_id,
        project_id=project_id,
        index_path=os.path.join(base_storage_path, "indexes", f"{repository_id}.faiss"),
        graph_path=os.path.join(base_storage_path, "graphs", f"{repository_id}_graph.pkl"),
        index_version=req.index_version,
        repository_version=req.repository_version,
        embedding_model=req.embedding_model,
        chunking_version=req.chunking_version
    )
    db_manager.insert("indexes", meta.model_dump())
    return meta

@router.get("/{project_id}/repositories/{repository_id}/indexes", response_model=List[IndexMetadata])
def list_index_metadata(project_id: str, repository_id: str, current_user: User = Depends(get_current_user)):
    proj = db_manager.find_one("projects", {"project_id": project_id, "owner_user_id": current_user.id})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    repo_doc = db_manager.find_one("repositories", {"repository_id": repository_id, "project_id": project_id})
    if not repo_doc:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    docs = db_manager.find("indexes", {"repository_id": repository_id, "project_id": project_id})
    return [IndexMetadata(**doc) for doc in docs]

from pydantic import BaseModel
class ProjectIngestRequest(BaseModel):
    backend: str = settings.DEFAULT_EMBEDDER_BACKEND
    force_reindex: bool = False

@router.post("/{project_id}/repositories/{repository_id}/sync/manifest", response_model=SyncManifestResponse)
def sync_manifest(
    project_id: str,
    repository_id: str,
    req: SyncManifestRequest,
    current_user: User = Depends(get_current_user)
):
    import logging
    logger = logging.getLogger(__name__)
    
    proj_doc = db_manager.find_one("projects", {"project_id": project_id})
    if not proj_doc:
        raise HTTPException(status_code=404, detail="Project not found")
    if proj_doc["owner_user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this project")

    repo_doc = db_manager.find_one("repositories", {"repository_id": repository_id, "project_id": project_id})
    if not repo_doc:
        raise HTTPException(status_code=404, detail="Repository not found in this project")
        
    if len(req.files) > 100000:
        raise HTTPException(status_code=400, detail="Too many files in manifest (limit 100000)")
        
    clean_manifest = {}
    for path, fhash in req.files.items():
        if ".." in path or path.startswith("/") or ":" in path or "\0" in path:
            raise HTTPException(status_code=400, detail=f"Invalid path in manifest: {path}")
        clean_path = path.replace("\\", "/")
        clean_manifest[clean_path] = fhash

    from core.persistence import get_repo_id, get_db_connection, load_stored_file_hashes
    
    internal_repo_id = get_repo_id(repo_doc["storage_path"])
    base_storage_path = os.path.join(".storage", "projects", current_user.id, project_id, "metadata")
    db_path = os.path.join(base_storage_path, "metadata.db")
    
    server_manifest = {}
    if os.path.exists(db_path):
        conn = get_db_connection(db_path)
        try:
            server_manifest = load_stored_file_hashes(conn, internal_repo_id)
        except Exception as e:
            logger.error(f"Error loading server manifest for {repository_id}: {e}")
        finally:
            conn.close()
            
    need = []
    delete = []
    unchanged = 0
    
    for path, client_hash in clean_manifest.items():
        if path not in server_manifest:
            need.append(path)
        elif server_manifest[path] != client_hash:
            need.append(path)
        else:
            unchanged += 1
            
    for path in server_manifest:
        if path not in clean_manifest:
            delete.append(path)
            
    return SyncManifestResponse(need=need, delete=delete, unchanged=unchanged)

@router.post("/{project_id}/repositories/{repository_id}/ingest", response_model=IndexMetadata)
def ingest_project_repository(project_id: str, repository_id: str, req: ProjectIngestRequest, current_user: User = Depends(get_current_user)):
    proj = db_manager.find_one("projects", {"project_id": project_id, "owner_user_id": current_user.id})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    repo_doc = db_manager.find_one("repositories", {"repository_id": repository_id, "project_id": project_id})
    if not repo_doc:
        raise HTTPException(status_code=404, detail="Repository not found")

    repo_model = Repository(**repo_doc)
    local_path = repo_model.source_path
    
    if not os.path.exists(local_path):
        raise HTTPException(status_code=400, detail=f"Source path '{local_path}' does not exist on server.")
        
    base_storage_path = repo_model.storage_path
    meta_storage_path = os.path.join(base_storage_path, "metadata")
    index_storage_path = os.path.join(base_storage_path, "indexes")
    db_path = os.path.join(meta_storage_path, "metadata.db")
    
    from backend.services.llm_factory import create_embedder, create_llm
    from core.pipeline import ingest_repository
    embedder = create_embedder(req.backend)
    llm = create_llm(req.backend)
    
    # Ingest using scoped paths
    result = ingest_repository(
        repo_path=local_path,
        embedder=embedder,
        force_reindex=req.force_reindex,
        save_to_disk=True,
        db_path=db_path,
        storage_dir=index_storage_path
    )
    
    from backend.dependency_graph import EnhancedDependencyGraph
    from backend.parser import parse_repository_files
    source_files = parse_repository_files(local_path)
    enhanced_graph_engine = EnhancedDependencyGraph()
    enhanced_graph = enhanced_graph_engine.build(source_files)
    
    from core.persistence import get_repo_id
    internal_repo_id = get_repo_id(local_path)
    graph_path = os.path.join(base_storage_path, "graphs", f"{internal_repo_id}_graph.pkl")
    
    import pickle
    try:
        os.makedirs(os.path.dirname(graph_path), exist_ok=True)
        with open(graph_path, "wb") as f:
            pickle.dump(enhanced_graph, f)
    except Exception as e:
        logger.warning(f"Failed to persist graph to {graph_path}: {e}")
    
    from rag.query_engine import QueryEngine
    engine = QueryEngine(result.store, embedder, llm)
    
    # Update ACTIVE_REPOS cache temporarily so /api/chat still works without redesign
    from backend.api.repos import ACTIVE_REPOS
    ACTIVE_REPOS[repository_id] = {
        "engine": engine,
        "graph": enhanced_graph,
        "store": result.store,
        "meta": {"repo_id": repository_id, "repo_path": local_path, "backend": req.backend},
        "source_files": source_files,
        "embedder": embedder,
    }
    
    from core.persistence import get_repo_id
    internal_repo_id = get_repo_id(local_path)
    
    index_id = generate_id("idx")
    meta = IndexMetadata(
        index_id=index_id,
        repository_id=repository_id,
        project_id=project_id,
        index_path=os.path.join(index_storage_path, f"{internal_repo_id}.faiss"),
        graph_path=graph_path,
        index_version="v1",
        repository_version=repo_model.current_version,
        embedding_model=req.backend,
        chunking_version="v1"
    )
    
    # Upsert index metadata (delete old for repo if exists, then insert)
    existing_indexes = db_manager.find("indexes", {"repository_id": repository_id, "project_id": project_id})
    if hasattr(db_manager, "delete_many"):
        db_manager.delete_many("indexes", {"repository_id": repository_id})
    else:
        # manual filter for LocalDiskStore
        if "indexes" in getattr(db_manager, "_data", {}):
            db_manager._data["indexes"] = [doc for doc in db_manager._data["indexes"] if doc.get("repository_id") != repository_id]
            if hasattr(db_manager, "_save"):
                db_manager._save()
                
    db_manager.insert("indexes", meta.model_dump())
    
    return meta
