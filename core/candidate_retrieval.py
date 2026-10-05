import logging
import networkx as nx
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field

from core.chunker import CodeChunk
from core.vectorstore import FaissVectorStore
from core.embedder import BaseEmbedder
from core.lexical_index import BM25Index

logger = logging.getLogger(__name__)


@dataclass
class Evidence:
    """Represents a piece of evidence for a retrieved candidate."""
    source_type: str  # 'semantic', 'lexical', or 'structural'
    raw_score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievedCandidate:
    """Represents a retrieved code chunk and its associated evidence."""
    chunk: CodeChunk
    file_path: str
    identifier: str  # e.g., chunk.chunk_id or chunk.name
    evidence: Evidence


@dataclass
class CandidateSet:
    """Independent sets of candidates retrieved from different engines."""
    semantic: List[RetrievedCandidate] = field(default_factory=list)
    lexical: List[RetrievedCandidate] = field(default_factory=list)
    structural: List[RetrievedCandidate] = field(default_factory=list)


class CandidateRetrieval:
    """
    Module 6: Candidate Retrieval
    Strictly responsible for retrieving candidates from independent sources
    (FAISS, BM25, NetworkX) without performing final weighted ranking.
    """

    def __init__(
        self,
        store: FaissVectorStore,
        embedder: BaseEmbedder,
        lexical_index: Optional[BM25Index] = None,
        dependency_graph: Optional[nx.DiGraph] = None,
        call_graph: Optional[nx.DiGraph] = None,
    ):
        self.store = store
        self.embedder = embedder
        self.lexical_index = lexical_index
        self.dependency_graph = dependency_graph
        self.call_graph = call_graph
        
        # Cache chunk lookup to prevent O(N) dict creation on every query
        self._chunk_lookup = {}
        if self.store and hasattr(self.store, "chunks") and self.store.chunks:
            self._chunk_lookup = {c.chunk_id: c for c in self.store.chunks}

    def retrieve(self, query: str, top_k: int = 10) -> CandidateSet:
        """
        Retrieves candidates independently from semantic, lexical, and structural sources.
        """
        cset = CandidateSet()

        # 1. Semantic Retrieval (FAISS)
        cset.semantic = self._retrieve_semantic(query, top_k)

        # 2. Lexical Retrieval (BM25)
        cset.lexical = self._retrieve_lexical(query, top_k)

        # 3. Structural Retrieval (NetworkX)
        cset.structural = self._retrieve_structural(query, top_k)

        return cset

    def _retrieve_semantic(self, query: str, top_k: int) -> List[RetrievedCandidate]:
        if not self.store or len(self.store) == 0:
            return []
        
        try:
            query_vec = self.embedder.embed([query])[0]
            results = self.store.search(query_vec, top_k=top_k)
        except Exception as e:
            logger.warning(f"Semantic retrieval failed: {e}")
            return []
            
        candidates = []
        for chunk, score in results:
            evidence = Evidence(source_type="semantic", raw_score=score)
            candidates.append(
                RetrievedCandidate(
                    chunk=chunk,
                    file_path=chunk.file_path,
                    identifier=chunk.chunk_id,
                    evidence=evidence
                )
            )
        return candidates

    def _retrieve_lexical(self, query: str, top_k: int) -> List[RetrievedCandidate]:
        if not self.lexical_index or len(self.lexical_index) == 0:
            return []
            
        try:
            results = self.lexical_index.search(query, top_k=top_k)
        except Exception as e:
            logger.warning(f"Lexical retrieval failed: {e}")
            return []
            
        candidates = []
        for chunk, score in results:
            evidence = Evidence(source_type="lexical", raw_score=score)
            candidates.append(
                RetrievedCandidate(
                    chunk=chunk,
                    file_path=chunk.file_path,
                    identifier=chunk.chunk_id,
                    evidence=evidence
                )
            )
        return candidates

    def _retrieve_structural(self, query: str, top_k: int) -> List[RetrievedCandidate]:
        """
        Independently searches the graph for nodes whose name or file path matches the query,
        and scores them based on their graph centrality (e.g., in_degree).
        """
        if not self.call_graph or len(self.call_graph) == 0:
            return []
            
        candidates = []
        query_lower = query.lower()
        
        node_scores = []
        for node_id, data in self.call_graph.nodes(data=True):
            name = data.get("name", "").lower()
            file_path = data.get("file_path", "").lower()
            
            if query_lower in name or query_lower in file_path:
                in_degree = self.call_graph.in_degree(node_id)
                node_scores.append((node_id, data, in_degree))
                
        node_scores.sort(key=lambda x: x[2], reverse=True)
        top_nodes = node_scores[:top_k]
        
        for node_id, data, in_degree in top_nodes:
            if node_id in self._chunk_lookup:
                chunk = self._chunk_lookup[node_id]
                evidence = Evidence(
                    source_type="structural", 
                    raw_score=float(in_degree),
                    metadata={"in_degree": in_degree}
                )
                candidates.append(
                    RetrievedCandidate(
                        chunk=chunk,
                        file_path=chunk.file_path,
                        identifier=chunk.chunk_id,
                        evidence=evidence
                    )
                )
                
        return candidates
