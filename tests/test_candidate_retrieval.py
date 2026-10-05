import pytest
import networkx as nx
import numpy as np

from core.chunker import CodeChunk
from core.vectorstore import FaissVectorStore
from core.lexical_index import BM25Index
from core.candidate_retrieval import CandidateRetrieval, CandidateSet


class DummyEmbedder:
    def embed(self, texts):
        return np.ones((len(texts), 64), dtype="float32")
    @property
    def dim(self):
        return 64


@pytest.fixture
def mock_chunks():
    return [
        CodeChunk(chunk_id="chunk1", file_path="auth.py", language="python", kind="function", name="login", start_line=1, end_line=10, code="def login(): pass", docstring=""),
        CodeChunk(chunk_id="chunk2", file_path="db.py", language="python", kind="function", name="connect", start_line=1, end_line=5, code="def connect(): pass", docstring=""),
        CodeChunk(chunk_id="chunk3", file_path="utils.py", language="python", kind="function", name="login_helper", start_line=1, end_line=5, code="def login_helper(): pass", docstring="")
    ]


@pytest.fixture
def candidate_retrieval_module(mock_chunks):
    store = FaissVectorStore(dim=64)
    vectors = np.array([
        [1.0] * 64,
        [0.8] * 64,
        [0.9] * 64
    ], dtype="float32")
    store.add(mock_chunks, vectors)

    lexical = BM25Index(chunks=mock_chunks)

    call_graph = nx.DiGraph()
    call_graph.add_node("chunk1", name="login", file_path="auth.py")
    call_graph.add_node("chunk2", name="connect", file_path="db.py")
    call_graph.add_node("chunk3", name="login_helper", file_path="utils.py")
    
    # chunk1 is highly central (in-degree 2)
    call_graph.add_edge("chunk2", "chunk1")
    call_graph.add_edge("chunk3", "chunk1")

    return CandidateRetrieval(
        store=store,
        embedder=DummyEmbedder(),
        lexical_index=lexical,
        dependency_graph=nx.DiGraph(),
        call_graph=call_graph
    )


def test_semantic_retrieval(candidate_retrieval_module):
    retrieval = candidate_retrieval_module
    cset = retrieval.retrieve("login", top_k=2)
    assert len(cset.semantic) == 2
    assert cset.semantic[0].evidence.source_type == "semantic"
    assert cset.semantic[0].evidence.raw_score > 0.0


def test_lexical_retrieval(candidate_retrieval_module):
    retrieval = candidate_retrieval_module
    cset = retrieval.retrieve("login", top_k=5)
    # BM25 should match 'login' in chunk1 and chunk3
    assert len(cset.lexical) == 2
    assert cset.lexical[0].evidence.source_type == "lexical"
    assert cset.lexical[0].evidence.raw_score > 0.0


def test_structural_retrieval(candidate_retrieval_module):
    retrieval = candidate_retrieval_module
    cset = retrieval.retrieve("login", top_k=5)
    # Should find chunk1 and chunk3 due to "login" in name
    assert len(cset.structural) == 2
    assert cset.structural[0].evidence.source_type == "structural"
    # chunk1 has higher in-degree (2) than chunk3 (0)
    assert cset.structural[0].identifier == "chunk1"
    assert cset.structural[0].evidence.raw_score == 2.0


def test_candidate_merging_structure_is_independent(candidate_retrieval_module):
    retrieval = candidate_retrieval_module
    cset = retrieval.retrieve("login")
    assert isinstance(cset, CandidateSet)
    assert isinstance(cset.semantic, list)
    assert isinstance(cset.lexical, list)
    assert isinstance(cset.structural, list)
    # Ensure they are independent candidate lists
    assert id(cset.semantic) != id(cset.lexical)
