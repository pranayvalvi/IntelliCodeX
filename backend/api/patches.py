"""
Patch Generator API Router (Phase 1)
Generates AI context-aware code patches, outputs Git diffs, confidence scores,
validates patches, and handles developer approval / application workflows.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from backend.services.loader import load_project_repository
from core.patch_generator import PatchEngine
from backend.auth import User, get_current_user
from backend.database import db_manager

router = APIRouter(prefix="/patches", tags=["Patch Generation Engine"])

class GeneratePatchRequest(BaseModel):
    repo_id: str
    project_id: Optional[str] = None
    error_report: str = Field(..., min_length=3, description="Bug report or stack trace")
    target_file: Optional[str] = None
    verify_in_sandbox: bool = False

class PatchApprovalRequest(BaseModel):
    patch_id: str
    status: str = Field(..., description="'approved' | 'rejected' | 'applied'")
    manual_edit: Optional[str] = Field(None, description="Developer-edited patch content")

@router.post("/generate")
def generate_patch(req: GeneratePatchRequest, current_user: User = Depends(get_current_user)):
    """
    Generate an AI-powered patch from a bug report or stack trace.

    Returns original code, suggested patch, git diff, explanation, and confidence score.
    """
    repo_data = load_project_repository(req.repo_id, current_user, req.project_id)
    
    from core.persistence import get_repo_id
    import os
    base_storage_path = repo_data["meta"]["storage_path"]
    internal_repo_id = get_repo_id(base_storage_path)
    server_repo_path = os.path.join(base_storage_path, "repository", internal_repo_id)

    engine = PatchEngine(
        store=repo_data["store"],
        embedder=repo_data["embedder"],
        llm=repo_data["engine"].llm,
        graph=repo_data.get("graph"),
        repo_path=server_repo_path,
        lexical_index=repo_data.get("lexical_index"),
    )
    return engine.generate_patch(req.repo_id, req.error_report, req.target_file, verify_in_sandbox=req.verify_in_sandbox)


@router.post("/approve")
def approve_patch(req: PatchApprovalRequest, current_user: User = Depends(get_current_user)):
    """Approve, reject, or apply a generated patch. Supports manual edits before applying."""
    if req.status not in ("approved", "rejected", "applied"):
        raise HTTPException(
            status_code=400,
            detail="Status must be 'approved', 'rejected', or 'applied'.",
        )

    record = db_manager.find_one("generated_patches", {"patch_id": req.patch_id})
    if not record:
        raise HTTPException(status_code=404, detail=f"Patch ID '{req.patch_id}' not found.")

    repo_data = load_project_repository(record["repo_id"], current_user, record.get("project_id"))
    
    from core.persistence import get_repo_id
    import os
    base_storage_path = repo_data["meta"]["storage_path"]
    internal_repo_id = get_repo_id(base_storage_path)
    server_repo_path = os.path.join(base_storage_path, "repository", internal_repo_id)

    engine = PatchEngine(
        store=repo_data["store"],
        embedder=repo_data["embedder"],
        llm=repo_data["engine"].llm,
        graph=repo_data.get("graph"),
        repo_path=server_repo_path,
        lexical_index=repo_data.get("lexical_index"),
    )

    updated = engine.update_patch_status(req.patch_id, req.status, req.manual_edit)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Patch ID '{req.patch_id}' not found.")

    if req.status == "applied" and updated.get("apply_result", {}).get("success") is False:
        raise HTTPException(
            status_code=500,
            detail=f"Patch application failed: {updated['apply_result'].get('error')}",
        )

    return updated


@router.get("/list/{repo_id}")
def list_patches(repo_id: str, current_user: User = Depends(get_current_user)):
    """List all generated patches for a repository, newest first."""
    patches = db_manager.find("generated_patches", {"repo_id": repo_id})
    return sorted(patches, key=lambda p: p.get("created_at", 0), reverse=True)
