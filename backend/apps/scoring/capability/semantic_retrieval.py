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


FUSION = 'protected-bm25-discovery-v4'
BASELINE_CHARS = 30000
EXPANSION_CHARS = 6000
ALLOCATION = 'protected-baseline-then-discovery-v2'
WIDE_ALLOCATION = 'protected-baseline-then-discovery-wide-v1'
XWIDE_ALLOCATION = 'protected-baseline-then-discovery-xwide-v1'
ALLOCATION_BUDGETS = {
    'protected-baseline-then-discovery-v1': (18000, 6000),
    ALLOCATION: (BASELINE_CHARS, EXPANSION_CHARS),
    # Multi-document sprints: a 90,000-character keyword lane (about three times the default packet).
    WIDE_ALLOCATION: (90000, EXPANSION_CHARS),
    # Full-corpus sprints where 90,000 still crowds out evidence. Needs CAPABILITY_MAX_INPUT_TOKEN_BOUND >= 400000.
    XWIDE_ALLOCATION: (200000, EXPANSION_CHARS),
}
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
    from . import structure
    routing = {}
    if settings.CAPABILITY_DEDUPLICATE_PAGES:
        routing['deduplicate'] = structure.DEDUPLICATE_VERSION
    if settings.CAPABILITY_STRUCTURE_ROUTING:
        routing['structure'] = structure.VERSION
    if getattr(settings, 'CAPABILITY_REPEAT_SKIP', False):
        routing['repeat_skip'] = structure.REPEAT_SKIP_VERSION
    if getattr(settings, 'CAPABILITY_FOLLOW_UP_SEARCH', False):
        from .follow_up import VERSION as FOLLOW_UP_VERSION
        if mode != 'hybrid' or getattr(settings, 'CAPABILITY_JUDGMENT', 'conditions') != 'parts':
            raise SemanticRetrievalUnavailable('CAPABILITY_FOLLOW_UP_SEARCH needs hybrid retrieval and CAPABILITY_JUDGMENT=parts.')
        routing['follow_up'] = FOLLOW_UP_VERSION
    allocation = settings.CAPABILITY_RETRIEVAL_ALLOCATION or ALLOCATION
    if allocation not in (ALLOCATION, WIDE_ALLOCATION, XWIDE_ALLOCATION):
        raise SemanticRetrievalUnavailable(
            f'CAPABILITY_RETRIEVAL_ALLOCATION must be {ALLOCATION}, {WIDE_ALLOCATION} or {XWIDE_ALLOCATION}.')
    if mode == 'bm25':
        if allocation != ALLOCATION:
            raise SemanticRetrievalUnavailable('The wide allocations need hybrid retrieval.')
        return {'mode': 'bm25', **routing}
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
            'lexical_weight': 2, 'semantic_weight': 1,
            'allocation': allocation,
            'baseline_chars': ALLOCATION_BUDGETS[allocation][0], 'expansion_chars': ALLOCATION_BUDGETS[allocation][1],
            'expansion_filter': 'instruction-heading-only-v2', **routing}


@lru_cache(maxsize=2)
def _model(path, model_name, fingerprint):
    import os
    os.environ['ORT_DISABLE_TELEMETRY'] = '1'
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=model_name, specific_model_path=path,
                         local_files_only=True, threads=2, providers=['CPUExecutionProvider'])


class EmbeddingCache:
    """Passage vectors on disk, keyed by the model artifact hash and the exact passage text.

    The encoder gives byte-identical vectors whatever the batch (checked: batch order and single-text
    calls match exactly), so a cached vector equals a fresh one and packets do not change. One SQLite file
    per model artifact; a different artifact never reads another's vectors."""

    def __init__(self, directory, artifact):
        import sqlite3
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / f'passages-{artifact[:16]}.sqlite3'
        self.connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self.connection.execute('CREATE TABLE IF NOT EXISTS vectors (text_hash TEXT PRIMARY KEY, vector BLOB NOT NULL)')
        self.connection.commit()

    @staticmethod
    def key(text):
        return hashlib.sha256(text.encode()).hexdigest()

    def get_many(self, texts):
        import numpy as np
        found = {}
        keys = {self.key(t): t for t in texts}
        items = list(keys)
        for start in range(0, len(items), 500):
            chunk = items[start:start + 500]
            rows = self.connection.execute(
                f'SELECT text_hash, vector FROM vectors WHERE text_hash IN ({",".join("?" * len(chunk))})', chunk)
            for text_hash, blob in rows:
                found[keys[text_hash]] = np.frombuffer(blob, dtype=np.float32).copy()
        return found

    def put_many(self, pairs):
        import numpy as np
        self.connection.executemany('INSERT OR IGNORE INTO vectors (text_hash, vector) VALUES (?, ?)',
                                    [(self.key(t), np.asarray(v, dtype=np.float32).tobytes()) for t, v in pairs])
        self.connection.commit()


class SemanticRanker:
    def __init__(self, model, tokenizer=None, token_limit=None, cache=None):
        self.model = model
        self.cache = cache
        self.baseline_chars = BASELINE_CHARS
        self.context_chars = BASELINE_CHARS + EXPANSION_CHARS
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
            from .evidence_retrieval import expansion_exclusion
            eligible = [p for p in passages if not expansion_exclusion(p)]
            texts = list(dict.fromkeys(p.embedding_text for p in eligible))
            cached = self.cache.get_many(texts) if self.cache is not None and texts else {}
            missing = [t for t in texts if t not in cached]
            vectors = list(self.model.passage_embed(missing, batch_size=32)) if missing else []
            if len(vectors) != len(missing):
                raise SemanticRetrievalUnavailable('Embedding response count mismatch.')
            if self.cache is not None and missing:
                self.cache.put_many(zip(missing, vectors))
            for text, value in list(cached.items()) + list(zip(missing, vectors)):
                self.vectors[text] = self._normalized(value)
            self.stats['cached_passages'] = len(cached)
            dimensions = len(next(iter(self.vectors.values()))) if self.vectors else 0
            self._matrix = np.stack([self.vectors[p.embedding_text] if not expansion_exclusion(p)
                else np.zeros(dimensions, dtype=np.float32) for p in passages])
            self.stats['embedded_passages'] += len(missing)
            self.stats['skipped_instruction_passages'] = len(passages) - len(eligible)
            self.stats['vector_bytes'] = self._matrix.nbytes
        result = []
        for query in queries:
            if not self._matrix.shape[1]:
                result.append(np.zeros(len(passages), dtype=np.float32))
                continue
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
    budgets = (policy.get('baseline_chars'), policy.get('expansion_chars'))
    if (policy.get('mode') != 'hybrid' or policy.get('fusion') != FUSION
            or policy.get('representation') != 'token-source-spans-v1' or policy.get('target_tokens') != 240
            or policy.get('query_policy') != 'evidence-record-profiles-1'
            or any(policy.get(key) != value for key, value in profiles.items())
            or policy.get('query_instruction') != query_instruction(settings.CAPABILITY_EMBEDDING_MODEL)
            or policy.get('lexical_weight') != 2
            or policy.get('semantic_weight') != 1
            or budgets != ALLOCATION_BUDGETS.get(policy.get('allocation'))
            or policy.get('expansion_filter') != 'instruction-heading-only-v2'
            or policy.get('model') != settings.CAPABILITY_EMBEDDING_MODEL
            or policy.get('fastembed_version') != version('fastembed')
            or policy.get('artifact_hash') != artifact_hash(settings.CAPABILITY_EMBEDDING_PATH)):
        raise SemanticRetrievalUnavailable('Frozen embedding model does not match the worker artifacts.')
    cache_dir = getattr(settings, 'CAPABILITY_EMBEDDING_CACHE_DIR', '')
    ranker = SemanticRanker(_model(settings.CAPABILITY_EMBEDDING_PATH, policy['model'], policy['artifact_hash']),
                            cache=EmbeddingCache(cache_dir, policy['artifact_hash']) if cache_dir else None)
    ranker.baseline_chars = budgets[0]
    ranker.context_chars = sum(budgets)
    return ranker
