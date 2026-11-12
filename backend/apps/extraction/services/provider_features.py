"""Explicit capabilities for Google's direct OpenAI-compatible endpoint.

Unknown proxies retain generic behaviour; a model name alone is not proof that
an intermediary forwards provider-specific options.
"""
from urllib.parse import urlsplit


def direct_gemini(base_url):
    return urlsplit(base_url or '').hostname == 'generativelanguage.googleapis.com'


def gemini_thinking(base_url, model):
    name = (model or '').rsplit('/', 1)[-1]
    return direct_gemini(base_url) and name.startswith(('gemini-2.5', 'gemini-3'))
