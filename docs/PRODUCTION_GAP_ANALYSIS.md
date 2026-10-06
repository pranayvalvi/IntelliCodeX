# IntelliCodeX Production Gap Analysis

## 1. Current Architecture
The current architecture is a hybrid local/remote model where the **CLI and the FastAPI Server both share identical core modules**. Currently, when a user executes the CLI on Windows, it runs the entire AI engine locally (parsing, chunking, FAISS index creation, sandbox testing, graph generation) and only communicates with the remote RunPod server to generate Ollama/Qwen embeddings and completions.
Simultaneously, the FastAPI server exposes basic endpoints (`/api/auth`, `/api/repos`, `/api/chat`) but relies on fragile in-memory global state (`ACTIVE_REPOS`) to track loaded projects.

## 2. Existing Capabilities
The project currently successfully implements a powerful intelligence engine consisting of:
- Multi-language AST parsing (Tree-Sitter & Regex fallbacks)
- Dual-strategy embeddings (Semantic + BM25 Lexical)
- Dependency & Call Graph generation
- Bug Localization (via Ochiai heuristics and semantic retrieval)
- Automated Patch Generation using Qwen2.5-Coder 14b
- Local Patch Validation (SandboxRunner executing test suites)

## 3. Working Capabilities
- **Model connectivity:** The LLM client successfully routes HTTP requests to remote Ollama servers.
- **RAG & Hybrid Search:** The core `QueryEngine` correctly expands queries using graphs and retrieves highly contextual source code chunks.
- **Test suite validation:** The local CLI correctly runs Pytest against patched repositories in a temporary local folder and verifies test passage.
- **Authentication:** `backend/auth/jwt_handler.py` provides working registration, login, and token generation endpoints.

## 4. Partial Capabilities
- **Project Isolation:** The backend accepts `repo_id` mappings, but stores everything in a global `.storage/` directory without cryptographic tenant isolation.
- **Persistence:** FAISS and SQLite persist to disk locally, but the FastAPI backend drops its entire memory of ingested projects upon restart because it relies on an in-memory `ACTIVE_REPOS` dictionary.
- **CLI/Client separation:** The CLI is currently a monolith that imports the `core/` engine directly, rather than operating purely via HTTP.

## 5. Missing Capabilities
- **Background Job Queue:** Long-running LLM and Sandbox generation tasks block the FastAPI thread. There is no job tracking system (QUEUED, RUNNING, COMPLETED).
- **Incremental Remote Sync:** The CLI cannot currently "sync" a local repository to the RunPod instance efficiently using hash diffs; it expects the backend to have direct filesystem access to the repo.
- **Repair History Persistence:** There is no database structure tracking historical patches, test results, or user decisions per project.
- **Isolated Docker Sandbox:** The `SandboxRunner` executes arbitrary code using `subprocess.Popen` directly on the host machine.

## 6. Technical Debt
- High coupling between the CLI presentation layer and the `core/` pipeline logic.
- Redundant persistence layers (SQLite and Mongo are both utilized, but state synchronization between them is lacking).
- `ACTIVE_REPOS` global dictionary in `backend/api/repos.py` prevents horizontal scaling and forces manual re-ingestion after reboots.

## 7. Security Risks
- **CRITICAL:** `SandboxRunner` provides no network, CPU, or memory isolation. A generated patch or user repository could execute `os.system("rm -rf /")` or establish reverse shells on the RunPod cloud machine.
- **CRITICAL:** Lack of strict `project_id` matching on read/write vector store operations could lead to data leakage between tenants.

## 8. Persistence Risks
- Backend restarts permanently lose the association between a user, their project, and the FAISS index files living in `.storage/`.
- System crashes during patch generation leave orphaned temporary directories on the disk.

## 9. Client/Server Coupling
- The CLI imports `core.pipeline.ingest_repository` and `rag.query_engine.QueryEngine` directly. If the CLI is deployed to a machine without the source repository present, it will crash.
- Transitioning to a true CLI Client requires hollowing out `cli.py` to route all commands through `client/api.py`.

## 10. Performance Risks
- Single-threaded FastAPI synchronous execution of `Qwen 14b` patch generation means one user request blocks the entire process.
- Re-ingesting entire repositories for 1-file changes wastes massive amounts of GPU time computing embeddings.

## 11. Testing Gaps
- Zero tests validating cross-project isolation (Tenant A attempting to read Tenant B's FAISS index).
- Zero tests validating that `SandboxRunner` accurately blocks network requests or filesystem escapes.
- No end-to-end tests utilizing purely the REST API (all E2E tests bypass FastAPI and use `PatchEngine` directly).

## 12. Proposed Migration Plan

| Requirement | Status | Existing Files | Risk | Required Change | Tests |
|:---|:---|:---|:---|:---|:---|
| Authentication | COMPLETE | `backend/auth/` | Low | None | Existing |
| Persistent Project Model | PARTIAL | `backend/api/repos.py` | High | Replace `ACTIVE_REPOS` with MongoDB documents. | `test_project_persistence.py` |
| Project Isolation | MISSING | `core/persistence.py` | High | Prefix storage paths with `projects/<user_id>/<project_id>/`. | `test_isolation.py` |
| Repository Sync | MISSING | N/A | Medium | Add file hashing to CLI, create `POST /sync` endpoint. | `test_incremental_sync.py` |
| Job System | MISSING | N/A | Medium | Implement async Redis/Queue or simple DB polling. | `test_job_queue.py` |
| Remote CLI | PARTIAL | `cli.py` | Medium | Strip `core/` imports, build `client/api.py`. | `test_cli_remote.py` |
| Secure Sandbox | NEEDS HARDENING | `core/sandbox_runner.py` | CRITICAL | Wrap execution in locked-down `docker run` shell. | `test_sandbox_security.py` |
| Repair History | MISSING | N/A | Low | Add MongoDB collection for Patch objects. | `test_history.py` |
| Hybrid RAG | COMPLETE | `rag/query_engine.py` | Low | Ensure it correctly respects isolated project paths. | Existing |

---

*Analysis performed successfully. 160 baseline tests passing perfectly.*
