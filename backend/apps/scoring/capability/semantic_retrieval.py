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


FUSION = 'source-passages-requirement-fusion-v2'
BGE_QUERY_INSTRUCTION = 'Represent this sentence for searching relevant passages: '


def query_instruction(model_name):
    return BGE_QUERY_INSTRUCTION if model_name in {
        'BAAI/bge-small-en-v1.5', 'BAAI/bge-base-en-v1.5', 'BAAI/bge-large-en-v1.5'} else ''


def configured_policy(mode=None):
    from django.conf import settings
    path = settings.CAPABILITY_EMBEDDING_PATH
    mode = mode or settings.CAPABILITY_RETRIEVAL_MODE
    if mode not in ('bm25', 'hybrid'):
        raise SemanticRetrievalUnavailable('CAPABILITY_RETRIEVAL_MODE must be bm25 or hybrid.')
    if mode == 'bm25':
        return {'mode': 'bm25'}
    from .query_profiles import profile_metadata
    profiles = profile_metadata()
    from importlib.metadata import version, PackageNotFoundError
    try:
        package_version = version('fastembed')
    except PackageNotFoundError as exc:
        raise SemanticRetrievalUnavailable('Install requirements/semantic.txt to enable local hybrid retrieval.') from exc
    return {'mode': 'hybrid', 'model': settings.CAPABILITY_EMBEDDING_MODEL,
            'artifact_hash': artifact_hash(path), 'fastembed_version': package_version,
            'fusion': FUSION, 'representation': 'token-source-spans-v1', 'target_tokens': 240,
            'query_policy': 'evidence-record-profiles-1', **profiles,
            'query_instruction': query_instruction(settings.CAPABILITY_EMBEDDING_MODEL),
            'lexical_weight': 2, 'semantic_weight': 1, 'lexical_budget_share': 0.5}


@lru_cache(maxsize=2)
def _model(path, model_name, fingerprint):
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=model_name, specific_model_path=path,
                         local_files_only=True, threads=2, providers=['CPUExecutionProvider'])


class SemanticRanker:
    def __init__(self, model, tokenizer=None, token_limit=None):
        self.model = model
        self.query_prefix = query_instruction(getattr(model, 'model_name', ''))
        # Private vectors live only for this run; no global source cache/index.
        self.vectors, self.queries, self._input_probes = {}, {}, {}
        self._tokenizer, self._token_limit = tokenizer, token_limit
        self._store_key, self._passages, self._matrix = None, None, None
        self.stats = {'corpus_builds': 0, 'corpus_reuses': 0, 'embedded_passages': 0}

    def _construction_tokenizer(self):
        if self._tokenizer is None:
            tokenizer = getattr(getattr(self.model, 'model', None), 'tokenizer', None)
            if tokenizer is None or not tokenizer.truncation:
                raise SemanticRetrievalUnavailable('Token-aware retrieval needs the provisioned tokenizer and its input limit.')
            from tokenizers import Tokenizer
            self._token_limit = tokenizer.truncation['max_length']
            self._tokenizer = Tokenizer.from_str(tokenizer.to_str())
            self._tokenizer.no_truncation()
            self._tokenizer.no_padding()
        return self._tokenizer

    @property
    def token_limit(self):
        self._construction_tokenizer()
        if not isinstance(self._token_limit, int) or self._token_limit < 64:
            raise SemanticRetrievalUnavailable('Invalid local encoder token allowance.')
        return self._token_limit

    def token_offsets(self, text):
        return self._construction_tokenizer().encode(text, add_special_tokens=False).offsets

    def passages(self, sources):
        from .passages import corpus_key, construct_passages
        signature = corpus_key(sources)
        if signature != self._store_key:
            self._passages = construct_passages(sources, self)
            self._store_key, self._matrix = signature, None
            self.vectors.clear()
            self._input_probes.clear()
            self.stats['corpus_builds'] += 1
        else:
            self.stats['corpus_reuses'] += 1
        return self._passages

    def similarities(self, passages, queries):
        import numpy as np
        if self._matrix is None:
            texts = list(dict.fromkeys(p.embedding_text for p in passages))
            vectors = list(self.model.passage_embed(texts, batch_size=32))
            if len(vectors) != len(texts):
                raise SemanticRetrievalUnavailable('Embedding response count mismatch.')
            for text, value in zip(texts, vectors):
                self.vectors[text] = self._normalized(value)
            self._matrix = np.stack([self.vectors[p.embedding_text] for p in passages])
            self.stats['embedded_passages'] += len(texts)
            self.stats['vector_bytes'] = self._matrix.nbytes
        result = []
        for query in queries:
            if query not in self.queries:
                values = list(self.model.query_embed(self.query_input(query)))
                if len(values) != 1:
                    raise SemanticRetrievalUnavailable('Query embedding response count mismatch.')
                self.queries[query] = self._normalized(values[0])
            try:
                result.append(self._matrix @ self.queries[query])
            except ValueError as exc:
                raise SemanticRetrievalUnavailable('Query and passage vector dimensions differ.') from exc
        return result

    def query_input(self, query):
        return self.query_prefix + query

    @staticmethod
    def _normalized(value):
        import numpy as np
        vector = np.asarray(value, dtype=np.float32)
        if vector.ndim != 1 or not np.all(np.isfinite(vector)) or not np.linalg.norm(vector):
            raise SemanticRetrievalUnavailable('Invalid local embedding vector.')
        return vector / np.linalg.norm(vector)

    def input_diagnostics(self, text):
        """Probe the provisioned tokenizer, without changing the live tokenizer's settings.

        This reports tokenizer coverage, not whether a table retains semantic meaning.
        """
        if text in self._input_probes:
            return self._input_probes[text]
        tokenizer = getattr(getattr(self.model, 'model', None), 'tokenizer', None)
        if tokenizer is None:
            return {'status': 'tokenizer_unavailable', 'input_chars': len(text)}
        from tokenizers import Tokenizer
        probe = Tokenizer.from_str(tokenizer.to_str())
        encoded = probe.encode(text)
        retained = max((end for _, end in encoded.offsets), default=0)
        limit = probe.truncation
        count = sum(encoded.attention_mask)
        probe.no_truncation()
        probe.no_padding()
        full = probe.encode(text)
        result = {'status': 'tokenizer_probed', 'input_chars': len(text), 'encoded_tokens': count,
                  'full_tokens': len(full.ids), 'truncation': limit, 'retained_chars': retained,
                  'truncated': count < len(full.ids)}
        self._input_probes[text] = result
        return result


def ranker_for(policy):
    if not policy or policy.get('mode') == 'bm25':
        return None
    from django.conf import settings
    from importlib.metadata import version
    from .query_profiles import profile_metadata
    profiles = profile_metadata()
    if (policy.get('mode') != 'hybrid' or policy.get('fusion') != FUSION
            or policy.get('representation') != 'token-source-spans-v1' or policy.get('target_tokens') != 240
            or policy.get('query_policy') != 'evidence-record-profiles-1'
            or any(policy.get(key) != value for key, value in profiles.items())
            or policy.get('query_instruction') != query_instruction(settings.CAPABILITY_EMBEDDING_MODEL)
            or policy.get('lexical_weight') != 2
            or policy.get('semantic_weight') != 1 or policy.get('lexical_budget_share') != 0.5
            or policy.get('model') != settings.CAPABILITY_EMBEDDING_MODEL
            or policy.get('fastembed_version') != version('fastembed')
            or policy.get('artifact_hash') != artifact_hash(settings.CAPABILITY_EMBEDDING_PATH)):
        raise SemanticRetrievalUnavailable('Frozen embedding model does not match the worker artifacts.')
    return SemanticRanker(_model(settings.CAPABILITY_EMBEDDING_PATH, policy['model'], policy['artifact_hash']))
