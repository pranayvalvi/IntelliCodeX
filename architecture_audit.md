# IntelliCodeX Architecture Audit: Client/Server Transition

## A. Current CLI Execution Flow
When the user executes `python cli.py <repo> -q "fix: <bug>"`, the system currently operates in a **hybrid local/remote state**:
1. **Initialization:** The CLI (`cli.py`) instantiates `OllamaEmbedder` and `OllamaLLM`. Due to the recent URL normalization patch, these successfully route HTTP traffic to the RunPod instance.
2. **Local Ingestion:** `cli.py` calls `ingest_repository()` locally on Windows. This walks the Windows file system, parses the AST, computes chunks, requests embeddings from RunPod over the network, and writes a FAISS index (`.storage/`) and SQLite DB locally to the Windows machine.
3. **Local Retrieval (RAG):** The CLI instantiates `QueryEngine` and runs FAISS similarity searches and BM25 ranking locally on the Windows machine.
4. **Patching & Sandboxing:** For `fix:` queries, `PatchEngine` requests a patch from RunPod's LLM, applies the patch to a temporary directory on Windows, and executes `SandboxRunner` (which runs `pytest`) locally on the Windows machine.

## B. Local-Only Components
In the target architecture, the Windows CLI should be extremely lightweight. The only components that truly belong on the local machine are:
- Command-line argument parsing and the interactive `prompt_toolkit` shell.
- `Rich` terminal UI rendering (tables, panels, markdown).
- Local file hash computation (to detect which files changed and need to be synced).
- Local patch application (receiving a validated diff from the server and applying it to the user's real working directory).

## C. Server-Side Components
The RunPod server (FastAPI + AI Engine) must absorb all heavy lifting:
- **Storage:** `core/persistence.py`, `core/vectorstore.py`, `core/lexical_index.py` (FAISS and SQLite).
- **Processing:** `core/parser.py`, `core/chunker.py`, `core/tree_sitter_chunker.py`.
- **Analysis:** `core/dependency_graph.py`, `core/call_graph.py`.
- **RAG:** `rag/query_engine.py`, `rag/candidate_retrieval.py`, `rag/hybrid_ranking.py`.
- **Execution:** `core/bug_localizer.py`, `core/patch_generator.py`, `core/sandbox_runner.py`.

## D. Components Safe to Remove
Since you explicitly noted that maintaining both local and remote implementations is unnecessary, we can safely remove:
1. Direct imports of `core/*` and `rag/*` from within `cli.py`.
2. Any `LocalBackend` facade or abstraction designed to toggle between local AI processing and remote AI processing.
3. The local file watcher (`backend/services/incremental_indexer.py`) from the CLI side, replacing it with a simple on-demand sync protocol.

## E. Components That Must Remain
- **The Core AI Engine:** `core/` and `rag/` must remain perfectly intact (per the strict 160-test baseline requirement).
- **The Backend API:** `backend/` must remain intact as the new entry point for all operations.
- **The Test Suite:** All `tests/*.py` files must be preserved.

## F. Components to Convert into a Remote Client
`cli.py` must be completely stripped of its AI logic and converted into a REST/HTTP client:
- **Ingestion:** Replaced by a `sync.py` script that computes a local hash manifest, diffs it against the server, and uploads only changed files to `/api/projects/{id}/sync/upload`.
- **Questions:** Replaced by streaming HTTP requests to `/api/chat/ask`.
- **Fixes:** Replaced by asynchronous job submission to `/api/projects/{id}/patches` and a polling loop checking `/api/jobs/{id}` for patch generation and sandbox results.

## G. Proposed Final Directory Structure
```text
IntelliCodeX/
├── client/                 # NEW: Lightweight Windows Client
│   ├── __init__.py
│   ├── api.py              # HTTP client wrapping RunPod FastAPI endpoints
│   ├── sync.py             # Hash manifest builder and file uploader
│   └── render.py           # Extracted Rich TUI rendering logic
├── cli.py                  # UPDATED: Thin entrypoint utilizing client/
├── backend/                # UNCHANGED: FastAPI Server & Job Queues
├── core/                   # UNCHANGED: Server-side AI engine
├── rag/                    # UNCHANGED: Server-side Retrieval
└── tests/                  # UNCHANGED: 160-test verification suite
```

## H. Exact Files to Change / Delete
- **Change:** `cli.py` (Delete all direct `core/` and `rag/` imports. Refactor to use `client/api.py`).
- **Change:** `core/pipeline.py` and `core/persistence.py` (Modify to accept isolated `projects/<project_id>/` paths instead of the hardcoded global `.storage/` directory, so multiple users don't overwrite each other's FAISS indices on the server).
- **Create:** `client/api.py`, `client/sync.py`, `client/render.py`.
- **Delete:** No files need to be deleted. We are purely refactoring `cli.py` and shifting the locus of execution.

## I. Risks and Tests That Must Be Run
1. **Security Risk (Sandbox):** Currently, `SandboxRunner` runs locally. If we move this to the RunPod server, it will be executing arbitrary, potentially malicious user test code on your cloud GPU. Before exposing this endpoint, `SandboxRunner` **must** be wrapped in a secure Docker container (`--network none`, memory limits, non-root user).
2. **Test Suite Breakage:** Many of the 160 existing tests likely invoke `PatchEngine`, `QueryEngine`, or `cli.py` directly. If we hollow out `cli.py`, any end-to-end CLI tests will fail unless they are mocked to simulate a running FastAPI server. We must ensure the `tests/` suite is carefully updated to test the `client/` abstraction against the FastAPI `backend/` routes.
