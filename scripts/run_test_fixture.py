import os
import sys
import json

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from core.embedder import OllamaEmbedder, TfidfEmbedder
from core.llm_client import OllamaLLM
from core.pipeline import ingest_repository
from core.patch_generator import PatchEngine
from core.sandbox_runner import SandboxRunner

def main():
    fixture_name = sys.argv[1] if len(sys.argv) > 1 else "bug_age_boundary"
    target_repo = os.path.join(repo_root, "fixtures", fixture_name)
    
    if len(sys.argv) > 2:
        error_report = sys.argv[2]
    elif fixture_name == "bug_missing_key":
        error_report = "When a user dictionary doesn't contain an 'email' key, the get_user_email function crashes with a KeyError instead of returning 'No Email' as documented."
    else:
        error_report = "18-year-old users should be allowed to vote, but the implementation uses > instead of >="
    
    print("1. Ingesting repository fixture...")
    # Use TFIDF embedder for speed unless Ollama is running
    embedder = TfidfEmbedder()
    llm = OllamaLLM(model="qwen2.5-coder")
    
    result = ingest_repository(target_repo, embedder, save_to_disk=False)
    
    print("2. Initializing Patch Engine (with Sandbox Verification)...")
    sandbox = SandboxRunner(default_timeout=15)
    patch_engine = PatchEngine(
        store=result.store,
        embedder=embedder,
        llm=llm,
        graph=result.graph,
        repo_path=target_repo,
        sandbox_runner=sandbox,
        lexical_index=result.lexical_index
    )
    
    print(f"3. Running AI Bug-Fixing Pipeline for: '{error_report}'")
    def progress(turn, max_t, msg):
        print(f"   [Sandbox] {msg}")

    patch_record = patch_engine.generate_and_verify_patch(
        repo_id="bug_age_boundary",
        error_report=error_report,
        target_file=None, # Auto-localize
        max_iterations=3,
        progress_callback=progress
    )
    
    print("\n================ RESULTS ================")
    print(f"Status: {patch_record.get('status')}")
    print(f"Target File Found: {patch_record.get('target_file')}")
    print(f"Confidence Score: {patch_record.get('confidence_score')}")
    print(f"Iterations: {patch_record.get('sandbox_validation', {}).get('iterations_count')}")
    print("\n--- Generated Git Diff ---")
    print(patch_record.get("git_diff"))
    print("\n--- Explanation ---")
    print(patch_record.get("explanation"))
    
    print("\nSandbox Verification Output:")
    print(json.dumps(patch_record.get("sandbox_validation"), indent=2))

if __name__ == "__main__":
    main()
