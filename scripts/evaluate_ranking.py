import os
import sys
import time
import statistics
import networkx as nx
from typing import List, Dict, Any, Tuple

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from core.embedder import TfidfEmbedder
from core.pipeline import ingest_repository
from core.bug_localizer import BugLocalizer
from core.hybrid_ranking import HybridRanking
from rag.query_engine import reciprocal_rank_fusion

# -------------------------------------------------------------------------
# 1. GROUND TRUTH DATASET
# -------------------------------------------------------------------------
GROUND_TRUTH = [
    {
        "id": "B001",
        "report": "TypeError: 'NoneType' object is not subscriptable at login when user doesn't exist",
        "expected_file": "pkg/auth.py",
        "expected_func": "authenticate"
    },
    {
        "id": "B002",
        "report": "KeyError: 'password_hash' missing from user dictionary record",
        "expected_file": "pkg/auth.py",
        "expected_func": "authenticate"
    },
    {
        "id": "B003",
        "report": "Exception: database connection failed or table users not found",
        "expected_file": "pkg/db.py",
        "expected_func": "get_user_by_username"
    }
]

# -------------------------------------------------------------------------
# 2. METRICS HELPERS
# -------------------------------------------------------------------------
def evaluate_ranking(candidates: List[Dict[str, Any]], expected_file: str, expected_func: str) -> int:
    """Returns the 1-based rank of the correct location, or 0 if not found."""
    for i, cand in enumerate(candidates):
        fp = cand.get("file_path", "").replace("\\", "/")
        fn = cand.get("function", "")
        # Fuzzy match path ending and function name
        if fp.endswith(expected_file) and (not expected_func or fn == expected_func):
            return i + 1
    return 0

def calc_metrics(ranks: List[int]) -> Dict[str, float]:
    top1 = sum(1 for r in ranks if r == 1) / len(ranks) if ranks else 0
    top3 = sum(1 for r in ranks if 1 <= r <= 3) / len(ranks) if ranks else 0
    top5 = sum(1 for r in ranks if 1 <= r <= 5) / len(ranks) if ranks else 0
    mrr = sum(1.0 / r for r in ranks if r > 0) / len(ranks) if ranks else 0
    return {"Top-1": top1, "Top-3": top3, "Top-5": top5, "MRR": mrr}

# -------------------------------------------------------------------------
# 3. EXPERIMENT RUNNER
# -------------------------------------------------------------------------
def run_benchmark():
    print("Initializing Experimental Framework...")
    embedder = TfidfEmbedder()
    # Ingest the test target
    repo_path = os.path.join(repo_root, "sample_repo")
    ingested = ingest_repository(repo_path, embedder, save_to_disk=False)
    
    # Initialize the baseline engine
    localizer = BugLocalizer(
        store=ingested.store, 
        embedder=embedder, 
        graph=ingested.graph, 
        lexical_index=ingested.lexical_index
    )

    configs = {
        "FAISS (Semantic)": {"alpha": 1.0, "beta": 0.0, "gamma": 0.0, "use_rrf": False},
        "BM25 (Lexical)": {"alpha": 0.0, "beta": 1.0, "gamma": 0.0, "use_rrf": False},
        "Structural": {"alpha": 0.0, "beta": 0.0, "gamma": 1.0, "use_rrf": False},
        "Sem + Lex": {"alpha": 0.5, "beta": 0.5, "gamma": 0.0, "use_rrf": False},
        "Sem + Str": {"alpha": 0.5, "beta": 0.0, "gamma": 0.5, "use_rrf": False},
        "Lex + Str": {"alpha": 0.0, "beta": 0.5, "gamma": 0.5, "use_rrf": False},
        "RRF (Baseline)": {"use_rrf": True},
        "AlphaBetaGamma Hybrid (Proposed)": {"alpha": 0.4, "beta": 0.3, "gamma": 0.3, "use_rrf": False},
    }

    results = {}
    latencies = {}

    print(f"\nRunning {len(GROUND_TRUTH)} benchmark queries over {len(configs)} configurations...")
    
    # WARM-UP (5 runs) and MEASUREMENT (30 runs) per config
    for config_name, params in configs.items():
        use_rrf = params.get("use_rrf", False)
        if not use_rrf:
            localizer.ranking = HybridRanking(
                alpha=params["alpha"], beta=params["beta"], gamma=params["gamma"]
            )
            
        # 1. Evaluate Accuracy
        ranks = []
        for bug in GROUND_TRUTH:
            if use_rrf:
                # Fallback to pure RRF for baseline measurement
                query = bug["report"]
                cset = localizer.retrieval.retrieve(query, top_k=20)
                # Convert candidate sets back to RRF tuples for evaluation simulation
                dense = [(c.chunk, c.evidence.raw_score) for c in cset.semantic]
                bm25 = [(c.chunk, c.evidence.raw_score) for c in cset.lexical]
                fused = reciprocal_rank_fusion([dense, bm25], k=60, top_k=5)
                # Convert back to dicts for rank evaluation
                candidates = [{"file_path": c[0].file_path, "function": c[0].name} for c in fused]
            else:
                res = localizer.localize(bug["report"], top_k=5)
                candidates = res["candidates"]
                
            rank = evaluate_ranking(candidates, bug["expected_file"], bug["expected_func"])
            ranks.append(rank)
        
        results[config_name] = calc_metrics(ranks)

        # 2. Evaluate Latency (35 iterations on bug 1: 5 warmup, 30 measure)
        sample_query = GROUND_TRUTH[0]["report"]
        lat_arr = []
        for i in range(35):
            t0 = time.perf_counter()
            if use_rrf:
                cset = localizer.retrieval.retrieve(sample_query, top_k=20)
                dense = [(c.chunk, c.evidence.raw_score) for c in cset.semantic]
                bm25 = [(c.chunk, c.evidence.raw_score) for c in cset.lexical]
                reciprocal_rank_fusion([dense, bm25], k=60, top_k=5)
            else:
                localizer.localize(sample_query, top_k=5)
            t1 = time.perf_counter()
            if i >= 5:  # skip warmup
                lat_arr.append((t1 - t0) * 1000)
                
        latencies[config_name] = {
            "mean": statistics.mean(lat_arr),
            "median": statistics.median(lat_arr),
            "std": statistics.stdev(lat_arr) if len(lat_arr) > 1 else 0
        }

    # -------------------------------------------------------------------------
    # PRINT EXPERIMENTAL RESULTS TABLE
    # -------------------------------------------------------------------------
    print("\n" + "="*80)
    print(f"{'Method':<25} | {'Top-1':<7} | {'Top-3':<7} | {'Top-5':<7} | {'MRR':<7} | {'Avg Lat (ms)'}")
    print("-" * 80)
    for method in ["FAISS (Semantic)", "BM25 (Lexical)", "RRF (Baseline)", "AlphaBetaGamma Hybrid (Proposed)"]:
        m = results[method]
        l = latencies[method]
        print(f"{method:<25} | {m['Top-1']:.2f}    | {m['Top-3']:.2f}    | {m['Top-5']:.2f}    | {m['MRR']:.2f}    | {l['mean']:.2f} +/- {l['std']:.2f}")

    # -------------------------------------------------------------------------
    # PRINT ABLATION STUDY
    # -------------------------------------------------------------------------
    print("\n" + "="*80)
    print("ABLATION STUDY: Contribution of Independent Evidence")
    print("-" * 80)
    print(f"{'Configuration':<25} | {'Top-1':<7} | {'Top-3':<7} | {'Top-5':<7} | {'MRR':<7}")
    print("-" * 80)
    for method in ["FAISS (Semantic)", "BM25 (Lexical)", "Structural", "Sem + Lex", "Sem + Str", "Lex + Str", "AlphaBetaGamma Hybrid (Proposed)"]:
        m = results[method]
        disp_name = method.replace(" (Proposed)", "").replace("FAISS ", "").replace("BM25 ", "")
        print(f"{disp_name:<25} | {m['Top-1']:.2f}    | {m['Top-3']:.2f}    | {m['Top-5']:.2f}    | {m['MRR']:.2f}")

    # -------------------------------------------------------------------------
    # WEIGHT SEARCH EXPERIMENT
    # -------------------------------------------------------------------------
    print("\n" + "="*80)
    print("WEIGHT SENSITIVITY STUDY (alpha / beta / gamma)")
    print("-" * 80)
    
    weights = [
        (0.6, 0.2, 0.2),
        (0.5, 0.3, 0.2),
        (0.4, 0.3, 0.3),
        (0.4, 0.4, 0.2),
        (0.3, 0.3, 0.4),
        (0.3, 0.4, 0.3),
        (0.2, 0.4, 0.4)
    ]
    
    print(f"{'Weights (a/b/g)':<25} | {'Top-1':<7} | {'Top-3':<7} | {'Top-5':<7} | {'MRR':<7}")
    print("-" * 80)
    for a, b, g in weights:
        localizer.ranking = HybridRanking(alpha=a, beta=b, gamma=g)
        ranks = []
        for bug in GROUND_TRUTH:
            res = localizer.localize(bug["report"], top_k=5)
            r = evaluate_ranking(res["candidates"], bug["expected_file"], bug["expected_func"])
            ranks.append(r)
        m = calc_metrics(ranks)
        w_str = f"{a:.1f} / {b:.1f} / {g:.1f}"
        print(f"{w_str:<25} | {m['Top-1']:.2f}    | {m['Top-3']:.2f}    | {m['Top-5']:.2f}    | {m['MRR']:.2f}")
    print("="*80)


if __name__ == "__main__":
    run_benchmark()
