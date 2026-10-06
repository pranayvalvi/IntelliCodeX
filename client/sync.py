import os
import hashlib
from typing import Dict

def build_manifest(path: str) -> Dict[str, str]:
    """
    Walks a local repository, ignoring common untracked/build folders,
    and returns a manifest dictionary of relative POSIX paths to SHA-256 hashes.
    """
    manifest = {}
    
    ignore_dirs = {".git", ".venv", "__pycache__", "node_modules", "build", "dist"}
    
    for root, dirs, files in os.walk(path):
        # Filter directories in-place to avoid traversing them
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
        
        for file in files:
            if file.endswith(".pyc") or file.endswith(".pyo") or file.startswith("."):
                continue
                
            file_path = os.path.join(root, file)
            # Ensure safe relative POSIX paths
            rel_path = os.path.relpath(file_path, path)
            rel_posix_path = rel_path.replace("\\", "/")
            
            # Compute hash by reading in chunks to prevent memory explosion
            sha256 = hashlib.sha256()
            try:
                with open(file_path, "rb") as f:
                    while chunk := f.read(8192):
                        sha256.update(chunk)
                manifest[rel_posix_path] = sha256.hexdigest()
            except (OSError, IOError):
                # Skip files we cannot read (permissions, locks, broken symlinks)
                continue
                
    return manifest
