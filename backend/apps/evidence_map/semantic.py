"""Semantic search over the evidence map's tag descriptions, for the map packet's fill (allocation
evidence-map-then-semantic-v1; CAPABILITY_MAP_FILL=semantic). Local embeddings only: no page text leaves the worker.

Why: the tagger already wrote, for every page it tagged, a short description of what the page records (its reason) and
the passage that shows it (its quote). Pages it tagged for *another* indicator can still be evidence here (an ERP page
tagged for data readiness may also show adoption). Searching those short, clean descriptions by meaning finds them
where keyword search over the raw page, full of tables and headers, does not.

What it does in a packet (packet.build, the fill): after the pages the tagger never read, half of the fill (starting
value) goes to tags for other indicators whose description is closest in meaning to one of this indicator's
requirements (its sentence and its record-language description), the requirements taking turns. Each such page is sent
as the usual window around the tag's quotation. The keyword fill then takes the rest, so every page stays reachable.

Routing only, as with the map: a tag's description is never shown to the judge and never earns credit; the judge quotes
the page text, and the quotation is checked as always.
"""
import hashlib

VERSION = 'tag-semantic-v1'
#: Share of the fill given to the semantic step (the rest stays with the keyword fill). Starting value.
SHARE = (1, 2)
STRENGTHS = ('direct', 'supporting')


def tag_text(tag):
    """The text a tag is searched by: what the tagger said the page records, and the passage it quoted."""
    return ' '.join(str(x).strip() for x in (tag.get('reason'), tag.get('quote')) if x and str(x).strip())


def queries_for(indicator, profiles=None):
    """{requirement id: search text}: the requirement's sentence and its record-language description."""
    if profiles is None:
        from apps.scoring.capability.query_profiles import _load
        profiles = _load()[0]
    out = {}
    for condition in indicator.get('conditions', []):
        profile = (profiles.get(condition['id']) or {}).get('query') or ''
        out[condition['id']] = f"{condition['text']} {profile}".strip()
    return out


class TagSearch:
    """Cosine similarity between requirement searches and tag descriptions.

    embed(texts, query) -> list of vectors. Vectors are cached by text (they are deterministic for one model artifact),
    so a run embeds each tag description once however many indicators read it."""

    def __init__(self, embed, *, name='', artifact=''):
        self.embed = embed
        self.name = name
        self.artifact = artifact
        self._vectors = {}

    def _get(self, texts, query):
        import numpy as np
        key = lambda t: ('q' if query else 'd', hashlib.sha256(t.encode()).hexdigest())
        missing = list(dict.fromkeys(t for t in texts if key(t) not in self._vectors))
        if missing:
            for text, vector in zip(missing, self.embed(missing, query)):
                v = np.asarray(vector, dtype=np.float32)
                norm = float(np.linalg.norm(v)) or 1.0
                self._vectors[key(text)] = v / norm
        return [self._vectors[key(t)] for t in texts]

    def similarities(self, queries, documents):
        """[[similarity of documents[j] to queries[i]]] (cosine, -1..1)."""
        if not queries or not documents:
            return [[] for _ in queries]
        import numpy as np
        q = np.stack(self._get(queries, True))
        d = np.stack(self._get(documents, False))
        return (q @ d.T).tolist()


def configured(policy):
    """A TagSearch for a run's frozen policy (fill 'semantic'), from the provisioned local model; raises
    SemanticRetrievalUnavailable when the model or its files are missing or differ from the run's."""
    from django.conf import settings
    from apps.scoring.capability.semantic_retrieval import (
        SemanticRetrievalUnavailable, _model, artifact_hash, query_instruction)
    path = getattr(settings, 'CAPABILITY_EMBEDDING_PATH', '')
    name = getattr(settings, 'CAPABILITY_EMBEDDING_MODEL', '')
    artifact = artifact_hash(path)
    frozen = policy.get('semantic') or {}
    if frozen.get('artifact_hash') and frozen['artifact_hash'] != artifact:
        raise SemanticRetrievalUnavailable('The embedding model on this worker differs from the one the run froze.')
    model = _model(path, name, artifact)
    prefix = query_instruction(name)

    def embed(texts, query):
        return list(model.embed([prefix + t for t in texts] if query else list(texts)))
    return TagSearch(embed, name=name, artifact=artifact)


def policy_entry():
    """The frozen policy's 'semantic' entry: refuses (SemanticRetrievalUnavailable) unless the library and the
    provisioned model are present, so a run never starts expecting semantic search it cannot do."""
    from importlib.metadata import PackageNotFoundError, version
    from django.conf import settings
    from apps.scoring.capability.semantic_retrieval import SemanticRetrievalUnavailable, artifact_hash
    try:
        package = version('fastembed')
    except PackageNotFoundError as exc:
        raise SemanticRetrievalUnavailable('CAPABILITY_MAP_FILL=semantic needs fastembed (requirements/semantic.txt) '
                                           'in this image.') from exc
    path = getattr(settings, 'CAPABILITY_EMBEDDING_PATH', '')
    return {'version': VERSION, 'share': '/'.join(map(str, SHARE)), 'strengths': list(STRENGTHS),
            'model': getattr(settings, 'CAPABILITY_EMBEDDING_MODEL', ''), 'artifact_hash': artifact_hash(path),
            'fastembed_version': package}
