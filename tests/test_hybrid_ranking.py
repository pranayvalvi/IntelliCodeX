import pytest
from core.chunker import CodeChunk
from core.candidate_retrieval import CandidateSet, RetrievedCandidate, Evidence
from core.hybrid_ranking import HybridRanking, RankedCandidate

@pytest.fixture
def dummy_chunks():
    return {
        "c1": CodeChunk(chunk_id="c1", file_path="f1.py", language="python", kind="func", name="n1", start_line=1, end_line=2, code="pass"),
        "c2": CodeChunk(chunk_id="c2", file_path="f2.py", language="python", kind="func", name="n2", start_line=1, end_line=2, code="pass"),
        "c3": CodeChunk(chunk_id="c3", file_path="f3.py", language="python", kind="func", name="n3", start_line=1, end_line=2, code="pass"),
    }

@pytest.fixture
def mock_candidate_set(dummy_chunks):
    # c1: strong semantic, weak lexical, no structural
    sem_c1 = RetrievedCandidate(chunk=dummy_chunks["c1"], file_path="f1.py", identifier="c1", evidence=Evidence("semantic", 0.9))
    lex_c1 = RetrievedCandidate(chunk=dummy_chunks["c1"], file_path="f1.py", identifier="c1", evidence=Evidence("lexical", 0.1))
    
    # c2: weak semantic, strong lexical, weak structural
    sem_c2 = RetrievedCandidate(chunk=dummy_chunks["c2"], file_path="f2.py", identifier="c2", evidence=Evidence("semantic", 0.2))
    lex_c2 = RetrievedCandidate(chunk=dummy_chunks["c2"], file_path="f2.py", identifier="c2", evidence=Evidence("lexical", 0.9))
    str_c2 = RetrievedCandidate(chunk=dummy_chunks["c2"], file_path="f2.py", identifier="c2", evidence=Evidence("structural", 1.0))
    
    # c3: strong structural, no semantic, no lexical
    str_c3 = RetrievedCandidate(chunk=dummy_chunks["c3"], file_path="f3.py", identifier="c3", evidence=Evidence("structural", 5.0))
    
    return CandidateSet(
        semantic=[sem_c1, sem_c2],
        lexical=[lex_c1, lex_c2],
        structural=[str_c2, str_c3]
    )

def test_weight_normalization():
    hr = HybridRanking(alpha=10, beta=10, gamma=20)
    assert hr.alpha == 0.25
    assert hr.beta == 0.25
    assert hr.gamma == 0.50

def test_negative_weights():
    with pytest.raises(ValueError):
        HybridRanking(alpha=-1)
        
def test_zero_weights():
    with pytest.raises(ValueError):
        HybridRanking(alpha=0, beta=0, gamma=0)

def test_hybrid_ranking_scores(mock_candidate_set):
    # Using equal weights (0.33, 0.33, 0.33)
    hr = HybridRanking(alpha=1, beta=1, gamma=1)
    results = hr.rank_weighted(mock_candidate_set, top_k=5)
    
    assert len(results) == 3
    # Check normalization for Semantic (min=0.2, max=0.9)
    # c1 sem_norm = 1.0
    # c2 sem_norm = 0.0
    
    # Check normalization for Lexical (min=0.1, max=0.9)
    # c1 lex_norm = 0.0
    # c2 lex_norm = 1.0
    
    # Check normalization for Structural (min=1.0, max=5.0)
    # c2 str_norm = 0.0
    # c3 str_norm = 1.0
    
    # Identify candidates in results
    res_map = {r.identifier: r for r in results}
    
    # c1 = 1.0*a + 0.0*b + 0.0*c = 1.0/3 = 0.333
    assert res_map["c1"].semantic_score == 1.0
    assert res_map["c1"].lexical_score == 0.0
    assert res_map["c1"].structural_score == 0.0
    assert abs(res_map["c1"].final_score - 0.333) < 0.01
    
    # c2 = 0.0*a + 1.0*b + 0.0*c = 1.0/3 = 0.333
    assert res_map["c2"].semantic_score == 0.0
    assert res_map["c2"].lexical_score == 1.0
    assert res_map["c2"].structural_score == 0.0
    assert abs(res_map["c2"].final_score - 0.333) < 0.01
    
    # c3 = 0.0*a + 0.0*b + 1.0*c = 1.0/3 = 0.333
    assert res_map["c3"].semantic_score == 0.0
    assert res_map["c3"].lexical_score == 0.0
    assert res_map["c3"].structural_score == 1.0
    assert abs(res_map["c3"].final_score - 0.333) < 0.01

def test_missing_evidence_is_zero(mock_candidate_set):
    hr = HybridRanking(alpha=1, beta=1, gamma=1)
    results = hr.rank_weighted(mock_candidate_set)
    res_map = {r.identifier: r for r in results}
    
    assert res_map["c3"].semantic_score == 0.0
    assert res_map["c3"].lexical_score == 0.0
    assert res_map["c1"].structural_score == 0.0

def test_rrf_baseline(mock_candidate_set):
    hr = HybridRanking()
    results = hr.rank_rrf_baseline(mock_candidate_set, k=60)
    
    # RRF only looks at semantic and lexical
    # c1 semantic rank 1 (score 0.9), lexical rank 2 (score 0.1)
    # c2 semantic rank 2 (score 0.2), lexical rank 1 (score 0.9)
    # c3 structural only, so no score in RRF!
    
    res_map = {r.identifier: r for r in results}
    
    assert "c3" not in res_map  # Baseline ignores structural
    
    c1_score = (1.0 / 61) + (1.0 / 62)
    c2_score = (1.0 / 62) + (1.0 / 61)
    
    assert abs(res_map["c1"].final_score - c1_score) < 0.0001
    assert abs(res_map["c2"].final_score - c2_score) < 0.0001
    
    # Tie breaking by identifier ascending means c1 should be first
    assert results[0].identifier == "c1"
    assert results[1].identifier == "c2"

def test_top_k_limiting(mock_candidate_set):
    hr = HybridRanking(alpha=1, beta=1, gamma=1)
    results = hr.rank_weighted(mock_candidate_set, top_k=2)
    assert len(results) == 2
