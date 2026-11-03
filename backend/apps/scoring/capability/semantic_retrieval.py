"""Local semantic candidate ranking. No evidence text leaves the worker.

Models must be provisioned explicitly. Assessment workers never download weights,
use hosted embedding APIs, or silently fall back when a frozen hybrid run fails.
"""
import hashlib
from functools import lru_cache
from pathlib import Path


class SemanticRetrievalUnavailable(ValueError):
    pass


def artifact_hash(path):
    root = Path(path)
    if not path or not (root / 'tokenizer.json').is_file():
        raise SemanticRetrievalUnavailable('Provision the local embedding model before enabling hybrid retrieval.')
    files = sorted(p for p in root.rglob('*') if p.is_file() and p.suffix in ('.onnx', '.json', '.txt'))
    if not any(p.suffix == '.onnx' for p in files) or not (root / 'tokenizer.json').is_file():
        raise SemanticRetrievalUnavailable('Provision the local embedding model before enabling hybrid retrieval.')
    signature = tuple((str(p.relative_to(root)), p.stat().st_size, p.stat().st_mtime_ns) for p in files)
    return _artifact_hash(str(root.resolve()), signature)


@lru_cache(maxsize=4)
def _artifact_hash(root, signature):
    digest = hashlib.sha256()
    for name, _, _ in signature:
        digest.update(name.encode())
        with (Path(root) / name).open('rb') as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(block)
    return digest.hexdigest()


def configured_policy():
    from django.conf import settings
    path = settings.CAPABILITY_EMBEDDING_PATH
    mode = settings.CAPABILITY_RETRIEVAL_MODE
    if mode not in ('bm25', 'hybrid'):
        raise SemanticRetrievalUnavailable('CAPABILITY_RETRIEVAL_MODE must be bm25 or hybrid.')
    if mode == 'bm25':
        return {'mode': 'bm25'}
    from importlib.metadata import version, PackageNotFoundError
    try:
        package_version = version('fastembed')
    except PackageNotFoundError as exc:
        raise SemanticRetrievalUnavailable('Install requirements/semantic.txt to enable local hybrid retrieval.') from exc
    return {'mode': 'hybrid', 'model': settings.CAPABILITY_EMBEDDING_MODEL,
            'artifact_hash': artifact_hash(path), 'fastembed_version': package_version,
            'fusion': 'reciprocal-rank-k60-top60', 'window_chars': 1200}


@lru_cache(maxsize=2)
def _model(path, model_name, fingerprint):
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=model_name, specific_model_path=path,
                         local_files_only=True, threads=2, providers=['CPUExecutionProvider'])


class SemanticRanker:
    def __init__(self, model):
        self.model = model
        # Private vectors live only for this run; no global source cache/index.
        self.vectors, self.queries = {}, {}

    def fuse(self, rows, lexical, query):
        import numpy as np
        missing = list(dict.fromkeys(row[2] for row in rows if row[2] not in self.vectors))
        if missing:
            values = list(self.model.passage_embed(missing, batch_size=32))
            if len(values) != len(missing):
                raise SemanticRetrievalUnavailable('Embedding response count mismatch.')
            for text, vector in zip(missing, values):
                vector = np.asarray(vector, dtype=float)
                if vector.ndim != 1 or not np.all(np.isfinite(vector)) or not np.linalg.norm(vector):
                    raise SemanticRetrievalUnavailable('Invalid local embedding vector.')
                self.vectors[text] = vector / np.linalg.norm(vector)
        if query not in self.queries:
            vector = np.asarray(list(self.model.query_embed(query))[0], dtype=float)
            if vector.ndim != 1 or not np.all(np.isfinite(vector)) or not np.linalg.norm(vector):
                raise SemanticRetrievalUnavailable('Invalid local query embedding.')
            self.queries[query] = vector / np.linalg.norm(vector)
        q = self.queries[query]
        def key(row):
            return row[0]['id'], row[1]
        def tie(row):
            return hashlib.sha256(row[0]['text'].encode()).hexdigest(), row[1], row[0]['id']
        semantic = sorted(rows, key=lambda row: (-float(self.vectors[row[2]] @ q), tie(row)))
        scores = {}
        for ranking in (lexical[:60], semantic[:60]):
            for rank, row in enumerate(ranking, start=1):
                scores[key(row)] = scores.get(key(row), 0) + 1 / (60 + rank)
        return sorted(rows, key=lambda row: (-scores.get(key(row), 0), tie(row)))


def ranker_for(policy):
    if not policy or policy.get('mode') == 'bm25':
        return None
    from django.conf import settings
    from importlib.metadata import version
    if (policy.get('mode') != 'hybrid' or policy.get('fusion') != 'reciprocal-rank-k60-top60'
            or policy.get('model') != settings.CAPABILITY_EMBEDDING_MODEL
            or policy.get('fastembed_version') != version('fastembed')
            or policy.get('artifact_hash') != artifact_hash(settings.CAPABILITY_EMBEDDING_PATH)):
        raise SemanticRetrievalUnavailable('Frozen embedding model does not match the worker artifacts.')
    return SemanticRanker(_model(settings.CAPABILITY_EMBEDDING_PATH, policy['model'], policy['artifact_hash']))
