import logging
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field

from core.chunker import CodeChunk
from core.candidate_retrieval import CandidateSet, RetrievedCandidate

logger = logging.getLogger(__name__)


@dataclass
class RankedCandidate:
    """Represents a fully scored and ranked candidate code chunk."""
    chunk: CodeChunk
    file_path: str
    identifier: str
    final_score: float
    semantic_score: float = 0.0
    lexical_score: float = 0.0
    structural_score: float = 0.0
    evidence_sources: List[str] = field(default_factory=list)


class HybridRanking:
    """
    Module 7: Hybrid Ranking
    Responsible for merging, deduplicating, normalizing, and calculating 
    the final weighted α/β/γ fusion score across independent evidence layers.
    """

    def __init__(self, alpha: float = 0.4, beta: float = 0.3, gamma: float = 0.3):
        self._set_weights(alpha, beta, gamma)

    def _set_weights(self, alpha: float, beta: float, gamma: float):
        """Validates and normalizes weights to sum to 1.0."""
        if alpha < 0 or beta < 0 or gamma < 0:
            raise ValueError("Weights must be non-negative.")
        
        total = alpha + beta + gamma
        if total == 0:
            raise ValueError("At least one weight must be greater than 0.")
        
        self.alpha = alpha / total
        self.beta = beta / total
        self.gamma = gamma / total
        logger.debug(f"HybridRanking weights normalized: α={self.alpha:.2f}, β={self.beta:.2f}, γ={self.gamma:.2f}")

    def _normalize_scores(self, raw_scores: Dict[str, float]) -> Dict[str, float]:
        """Min-Max normalization to scale scores to [0, 1]."""
        if not raw_scores:
            return {}
        
        max_score = max(raw_scores.values())
        min_score = min(raw_scores.values())
        
        if max_score == min_score:
            # If all scores are identical, assign them 1.0 if >0 else 0.0
            return {k: (1.0 if v > 0 else 0.0) for k, v in raw_scores.items()}
            
        return {
            k: (v - min_score) / (max_score - min_score) 
            for k, v in raw_scores.items()
        }

    def rank_weighted(self, candidate_set: CandidateSet, top_k: int = 10) -> List[RankedCandidate]:
        """
        Merges candidates and applies the α*Sem + β*Lex + γ*Str formula.
        """
        # 1. Merge and aggregate raw scores
        raw_sem: Dict[str, float] = {}
        raw_lex: Dict[str, float] = {}
        raw_str: Dict[str, float] = {}
        chunks_map: Dict[str, CodeChunk] = {}
        
        for cand in candidate_set.semantic:
            raw_sem[cand.identifier] = cand.evidence.raw_score
            chunks_map[cand.identifier] = cand.chunk
            
        for cand in candidate_set.lexical:
            raw_lex[cand.identifier] = cand.evidence.raw_score
            chunks_map[cand.identifier] = cand.chunk
            
        for cand in candidate_set.structural:
            raw_str[cand.identifier] = cand.evidence.raw_score
            chunks_map[cand.identifier] = cand.chunk

        # 2. Normalize each evidence source independently
        norm_sem = self._normalize_scores(raw_sem)
        norm_lex = self._normalize_scores(raw_lex)
        norm_str = self._normalize_scores(raw_str)

        # 3. Calculate final hybrid scores
        results = []
        for identifier, chunk in chunks_map.items():
            sem_score = norm_sem.get(identifier, 0.0)
            lex_score = norm_lex.get(identifier, 0.0)
            str_score = norm_str.get(identifier, 0.0)
            
            final_score = (
                self.alpha * sem_score +
                self.beta * lex_score +
                self.gamma * str_score
            )
            
            evidence_sources = []
            if identifier in norm_sem: evidence_sources.append("semantic")
            if identifier in norm_lex: evidence_sources.append("lexical")
            if identifier in norm_str: evidence_sources.append("structural")

            results.append(
                RankedCandidate(
                    chunk=chunk,
                    file_path=chunk.file_path,
                    identifier=identifier,
                    final_score=final_score,
                    semantic_score=sem_score,
                    lexical_score=lex_score,
                    structural_score=str_score,
                    evidence_sources=evidence_sources
                )
            )

        # 4. Sort and Top-K
        # Sort by final score descending. If tie, sort by identifier ascending for determinism.
        results.sort(key=lambda x: (-x.final_score, x.identifier))
        return results[:top_k]

    def rank_rrf_baseline(self, candidate_set: CandidateSet, top_k: int = 10, k: int = 60) -> List[RankedCandidate]:
        """
        Reciprocal Rank Fusion (RRF) baseline.
        Ignores structural evidence to replicate the original Intelli-Codex baseline.
        Formula: 1 / (k + rank)
        """
        rrf_scores: Dict[str, float] = {}
        chunks_map: Dict[str, CodeChunk] = {}
        evidence_map: Dict[str, Set[str]] = {}

        # Process Semantic Ranks
        sem_sorted = sorted(candidate_set.semantic, key=lambda x: x.evidence.raw_score, reverse=True)
        for rank, cand in enumerate(sem_sorted):
            ident = cand.identifier
            chunks_map[ident] = cand.chunk
            rrf_scores[ident] = rrf_scores.get(ident, 0.0) + 1.0 / (k + rank + 1)
            evidence_map.setdefault(ident, set()).add("semantic")

        # Process Lexical Ranks
        lex_sorted = sorted(candidate_set.lexical, key=lambda x: x.evidence.raw_score, reverse=True)
        for rank, cand in enumerate(lex_sorted):
            ident = cand.identifier
            chunks_map[ident] = cand.chunk
            rrf_scores[ident] = rrf_scores.get(ident, 0.0) + 1.0 / (k + rank + 1)
            evidence_map.setdefault(ident, set()).add("lexical")

        # Note: Baseline RRF did not include structural ranks.
        
        results = []
        for ident, score in rrf_scores.items():
            chunk = chunks_map[ident]
            results.append(
                RankedCandidate(
                    chunk=chunk,
                    file_path=chunk.file_path,
                    identifier=ident,
                    final_score=score,
                    evidence_sources=list(evidence_map[ident])
                )
            )

        results.sort(key=lambda x: (-x.final_score, x.identifier))
        return results[:top_k]
