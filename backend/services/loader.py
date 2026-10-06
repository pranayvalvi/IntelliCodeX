import os
import logging
from typing import Dict, Any, Optional

from fastapi import HTTPException
from backend.database import db_manager
from backend.config import settings
from backend.auth import User
from backend.services.llm_factory import create_embedder, create_llm

logger = logging.getLogger(__name__)

def load_project_repository(repository_id: str, current_user: User, project_id: Optional[str] = None) -> Dict[str, Any]:
    from backend.api.repos import ACTIVE_REPOS, get_repo_engine
    
    # Fast path: already in cache
    if repository_id in ACTIVE_REPOS:
        backend = settings.DEFAULT_EMBEDDER_BACKEND
        if ACTIVE_REPOS[repository_id]["engine"].llm is None and backend == "ollama":
            ACTIVE_REPOS[repository_id]["engine"].llm = create_llm("ollama")
        return ACTIVE_REPOS[repository_id]
        
    # Attempt to resolve persistent repository
    repo_query = {"repository_id": repository_id}
    if project_id:
        repo_query["project_id"] = project_id
        
    repo_doc = db_manager.find_one("repositories", repo_query)
    
    if not repo_doc:
        # Fallback to legacy global behavior for backward compatibility
        try:
            return get_repo_engine(repository_id)
        except HTTPException:
            raise HTTPException(status_code=404, detail="Repository not found in project or globally.")

    resolved_project_id = repo_doc["project_id"]
    
    # Verify ownership
    proj_doc = db_manager.find_one("projects", {"project_id": resolved_project_id, "owner_user_id": current_user.id})
    if not proj_doc:
        raise HTTPException(status_code=403, detail="Not authorized to access this repository's project.")
        
    # Look up IndexMetadata
    idx_doc = db_manager.find_one("indexes", {"repository_id": repository_id, "project_id": resolved_project_id})
    if not idx_doc:
        raise HTTPException(status_code=404, detail="Index metadata not found for this repository.")
        
    index_path = idx_doc.get("index_path")
    if not index_path or not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Physical FAISS index file is missing from disk.")
        
    # Load core index
    from core.vectorstore import FaissVectorStore
    try:
        # load FAISS directly since we don't have chunks inline in FAISS anymore? 
        # Wait, how does load_index work in core.persistence?
        # Actually, FaissVectorStore.load(index_path) works, but where do we get chunks?
        from core.persistence import load_index
        db_path = os.path.join(repo_doc["storage_path"], "metadata", "metadata.db")
        storage_dir = os.path.join(repo_doc["storage_path"], "indexes")
        
        # the repo_path param for load_index is usually the original source_path
        local_path = repo_doc.get("source_path", repo_doc.get("local_path"))
        
        cached_data = load_index(local_path, db_path=db_path, storage_dir=storage_dir)
        if not cached_data:
            raise HTTPException(status_code=500, detail="Failed to load index from metadata.db.")
            
        meta, chunks, store = cached_data
    except Exception as e:
        logger.error(f"Failed to load project index: {e}")
        raise HTTPException(status_code=500, detail="Failed to load persistent index.")
        
    backend = idx_doc.get("embedding_model", settings.DEFAULT_EMBEDDER_BACKEND)
    embedder = create_embedder(backend)
    llm = create_llm(backend)
    
    from backend.dependency_graph import EnhancedDependencyGraph
    from backend.parser import parse_repository_files
    import pickle
    
    source_files = parse_repository_files(local_path) if local_path and os.path.exists(local_path) else []
    
    enhanced_graph = None
    graph_path = idx_doc.get("graph_path")
    if graph_path and os.path.exists(graph_path):
        try:
            with open(graph_path, "rb") as f:
                enhanced_graph = pickle.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cached graph from {graph_path}: {e}")
            
    if not enhanced_graph:
        enhanced_graph = EnhancedDependencyGraph().build(source_files) if source_files else EnhancedDependencyGraph().build([])
    
    from rag.query_engine import QueryEngine
    engine = QueryEngine(store, embedder, llm)
    
    # Populate ACTIVE_REPOS as runtime cache
    ACTIVE_REPOS[repository_id] = {
        "engine": engine,
        "graph": enhanced_graph,
        "store": store,
        "meta": repo_doc,
        "source_files": source_files,
        "embedder": embedder,
    }
    
    return ACTIVE_REPOS[repository_id]
