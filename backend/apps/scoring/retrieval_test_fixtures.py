"""Deterministic test tokenizer; real encoder/tokenizer contracts run separately offline."""
import re
from types import SimpleNamespace
from .capability.semantic_retrieval import SemanticRanker


class WordTokenizer:
    def encode(self, text, add_special_tokens=False):
        offsets = [match.span() for match in re.finditer(r'\w+|[^\w\s]', text)]
        return SimpleNamespace(offsets=offsets, ids=list(range(len(offsets))))


def synthetic_ranker(model, limit=512):
    return SemanticRanker(model, tokenizer=WordTokenizer(), token_limit=limit)
