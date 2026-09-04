"""Vector-store services.

Layered so each piece is replaceable on its own:

* `chunking`        — pure text splitting; no Django, no network
* `embeddings`      — provider-agnostic embedding, behind `get_embedding_service()`
* `pinecone_client` — the only module that imports the Pinecone SDK
* `indexer`         — document → chunks → embeddings → upsert, plus the tracking row
* `search`          — the read path the future benchmarking layer will call
"""
from .chunking import chunk_pages, clean_text
from .embeddings import get_embedding_service
from .indexer import index_document, is_enabled, queue_document
from .search import search_college_evidence

__all__ = [
    'chunk_pages',
    'clean_text',
    'get_embedding_service',
    'index_document',
    'is_enabled',
    'queue_document',
    'search_college_evidence',
]
