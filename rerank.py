from sentence_transformers import CrossEncoder
import numpy as np


class Reranker:
    def __init__(self, model_name: str = "Alibaba-NLP/gte-multilingual-reranker-base"):
        """Cross-Encoder reranker wrapper.

        Args:
            model_name: HuggingFace model name for CrossEncoder.
        """
        self.reranker = CrossEncoder(model_name, trust_remote_code=True)

    def __call__(self, query: str, passages: list[str]):
        """Score and sort passages by relevance to query.

        Returns:
            ranked_scores: list[float] sorted desc
            ranked_passages: list[str] sorted desc by score
        """
        if not passages:
            return [], []

        # Combine query and passages into pairs
        pairs = [[query, p] for p in passages]

        # Get scores from the reranker model (numpy array)
        scores = self.reranker.predict(pairs)

        # Sort passages based on scores (descending)
        ranked = sorted(zip(scores, passages), key=lambda x: x[0], reverse=True)
        ranked_scores = [float(s) for s, _ in ranked]
        ranked_passages = [p for _, p in ranked]
        return ranked_scores, ranked_passages
