"""Stage 4: the daily source watcher.

For every ENABLED SourceFeed (feeds are created disabled; a person turns one on):
  fetch -> normalize -> hash -> compare with the last snapshot -> change events.

What is compared (so daily noise -- dates, visitor counters, session tokens --
doesn't raise alarms):
  document_index pages  the list of linked documents (text + absolute URL)
  web_page pages        the visible text, line by line, minus volatile lines
  files (PDF etc.)      the bytes (SHA-256)

Events (schema: source_change_events): new_document, new_version, content_change,
withdrawal, access_change -- each with a 0-100 materiality score, a plain summary,
the added/removed links or lines, and an impact list (approved requirements from
the source, benchmarks linked to them, published releases containing those).

Never automatic: the watcher only records; a person reviews each event
(ignore / under review / accept / reject). It never edits a source, requirement,
benchmark or release.

Politeness: robots.txt is respected, one request per feed per run, a pause
between requests to the same host, and an honest User-Agent.
"""
import difflib
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import (
    BenchmarkRelease, BenchmarkRequirement, Requirement, SourceAuditEvent, SourceChangeEvent, SourceFeed,
    SourceSnapshot, WatcherRun,
)

logger = logging.getLogger(__name__)

USER_AGENT = 'InGage-SourceWatcher/1.0 (daily check of official education-regulation pages)'
TIMEOUT = 30
MAX_BYTES = 20 * 1024 * 1024
HOST_PAUSE_SECONDS = 2
DOC_EXT = re.compile(r'\.(pdf|docx?|xlsx?|pptx?|odt|zip)(\?|#|$)', re.I)
VOLATILE = re.compile(r'(visitor|hits?\s*:|last\s+(updated|modified|reviewed)|page\s+views|©|copyright|'
                      r'\b\d{1,2}:\d{2}(:\d{2})?\b|\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s+\d)', re.I)
NUMBERS_ONLY = re.compile(r'^[\d\s,.:/|-]+$')  # bare counters, dates, page numbers
KEY_TERMS = re.compile(r'regulation|amendment|notification|guideline|manual|\bsar\b|\bssr\b|norms|circular|'
                       r'policy|framework|handbook|gazette|rules|directions?', re.I)
SNAPSHOT_DIR = 'source_snapshots'


class FetchError(Exception):
    def __init__(self, message, *, status=None, kind='network'):
        super().__init__(message)
        self.status, self.kind = status, kind


@dataclass
class Fetched:
    url: str
    status: int
    content: bytes
    content_type: str
    headers: dict


_robots_cache = {}


def robots_allows(url):
    parts = urlsplit(url)
    root = f'{parts.scheme}://{parts.netloc}'
    if root not in _robots_cache:
        rp = RobotFileParser()
        try:
            import requests
            resp = requests.get(f'{root}/robots.txt', headers={'User-Agent': USER_AGENT}, timeout=10)
            rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
        except Exception:
            rp.parse([])  # robots.txt unreachable -> treat as no restrictions
        _robots_cache[root] = rp
    return _robots_cache[root].can_fetch(USER_AGENT, url)


_last_hit = {}


def fetch(url):
    import requests

    if not robots_allows(url):
        raise FetchError('robots.txt disallows automated access to this page.', kind='robots')
    host = urlsplit(url).netloc
    wait = HOST_PAUSE_SECONDS - (time.monotonic() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.monotonic()
    try:
        resp = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=TIMEOUT, stream=True)
        content = resp.raw.read(MAX_BYTES + 1, decode_content=True)
    except requests.RequestException as exc:
        raise FetchError(f'{type(exc).__name__}: {exc}'[:300], kind='network')
    if resp.status_code >= 400:
        raise FetchError(f'HTTP {resp.status_code}', status=resp.status_code, kind='http')
    if len(content) > MAX_BYTES:
        raise FetchError(f'Larger than {MAX_BYTES // (1024 * 1024)} MB; not stored.', kind='size')
    return Fetched(url=resp.url, status=resp.status_code, content=content,
                   content_type=resp.headers.get('Content-Type', ''),
                   headers={k: resp.headers.get(k, '') for k in ('Content-Type', 'ETag', 'Last-Modified', 'Content-Length')})


# -- normalizing ---------------------------------------------------------------------

def _is_html(f):
    return 'html' in f.content_type.lower() or f.content[:200].lstrip().lower().startswith((b'<!doctype', b'<html'))


def normalize(feed, f):
    """(normalized dict, hash) -- the part of the page that is compared."""
    if feed.feed_type == SourceFeed.FeedType.RSS:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(f.content, 'html.parser')
        items = set()
        for it in soup.find_all(['item', 'entry']):
            title = ' '.join((it.find('title').get_text(' ') if it.find('title') else '').split())[:300]
            link = it.find('link')
            href = (link.get('href') or link.get_text() or (link.next_sibling or '')).strip() if link else ''
            items.add((title, urljoin(f.url, str(href).strip())))
        data = {'links': sorted(items)}
        return data, hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    if not _is_html(f):
        return {'binary': True, 'bytes': len(f.content)}, hashlib.sha256(f.content).hexdigest()
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(f.content, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'iframe']):
        tag.decompose()
    if feed.feed_type == SourceFeed.FeedType.DOCUMENT_INDEX:
        links = set()
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue
            absolute = urljoin(f.url, href)
            if DOC_EXT.search(absolute):
                links.add((' '.join(a.get_text(' ').split())[:300], absolute))
        data = {'links': sorted(links)}
    else:
        lines = [' '.join(ln.split()) for ln in soup.get_text('\n').splitlines()]
        data = {'text_lines': [ln for ln in lines if ln and not VOLATILE.search(ln) and not NUMBERS_ONLY.match(ln)]}
    return data, hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def store_raw(f):
    sha = hashlib.sha256(f.content).hexdigest()
    ext = '.html' if _is_html(f) else (os.path.splitext(urlsplit(f.url).path)[1][:10] or '.bin')
    rel = f'{SNAPSHOT_DIR}/{sha[:2]}/{sha}{ext}'
    path = os.path.join(settings.MEDIA_ROOT, rel)
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.part', 'wb') as fh:
            fh.write(f.content)
        os.replace(path + '.part', path)
    return rel


# -- comparing -------------------------------------------------------------------------

def compare(old, new):
    """[(kind, materiality, summary, details)] between two normalized snapshots."""
    if new.get('binary') or old.get('binary'):
        return [(SourceChangeEvent.Kind.NEW_VERSION, 80, 'The file changed: a new version or a corrected file '
                 'was published at the same address.', {'old_bytes': old.get('bytes'), 'new_bytes': new.get('bytes')})]
    if 'links' in new:
        before = {tuple(x) for x in old.get('links', [])}
        after = {tuple(x) for x in new['links']}
        added, removed = sorted(after - before), sorted(before - after)
        out = []
        if added:
            key = [t for t, _ in added if KEY_TERMS.search(t)]
            score = min(95, 40 + 15 * len(key) + 5 * (len(added) - len(key)))
            out.append((SourceChangeEvent.Kind.NEW_DOCUMENT, score,
                        f'{len(added)} new document link(s) listed' + (f', e.g. "{added[0][0] or added[0][1]}"' if added else '') + '.',
                        {'added': [list(x) for x in added[:50]]}))
        if removed:
            out.append((SourceChangeEvent.Kind.WITHDRAWAL, min(80, 40 + 5 * len(removed)),
                        f'{len(removed)} document link(s) no longer listed.', {'removed': [list(x) for x in removed[:50]]}))
        return out
    a, b = old.get('text_lines', []), new.get('text_lines', [])
    diff = [d for d in difflib.unified_diff(a, b, lineterm='', n=0) if d[:1] in '+-' and d[:3] not in ('+++', '---')]
    plus = [d[1:] for d in diff if d.startswith('+')]
    minus = [d[1:] for d in diff if d.startswith('-')]
    if not plus and not minus:
        return []
    ratio = (len(plus) + len(minus)) / max(1, len(a) + len(b))
    score = round(min(90, 20 + ratio * 200 + (15 if any(KEY_TERMS.search(x) for x in plus) else 0)), 2)
    return [(SourceChangeEvent.Kind.CONTENT_CHANGE, score,
             f'Page text changed: {len(plus)} line(s) added, {len(minus)} removed.',
             {'added_lines': plus[:30], 'removed_lines': minus[:30]})]


def impact(document):
    reqs = list(Requirement.objects.filter(version__document=document).values_list('code', flat=True))
    links = BenchmarkRequirement.objects.filter(requirement__version__document=document)
    benches = sorted(set(links.values_list('benchmark__benchmark_code', flat=True)))
    rels = sorted(set(BenchmarkRelease.objects.filter(
        status=BenchmarkRelease.Status.PUBLISHED, items__benchmark__benchmark_code__in=benches,
    ).values_list('release_label', flat=True)))
    note = ('' if reqs else 'No approved requirements come from this source yet, so nothing scored depends on it.')
    return {'requirements': reqs, 'benchmarks': benches, 'published_releases': rels, 'note': note}


# -- one feed / one run -------------------------------------------------------------------

def _event(feed, kind, score, summary, details, prev=None, cur=None):
    return SourceChangeEvent.objects.create(
        document=feed.document, feed=feed, previous_snapshot=prev, current_snapshot=cur, change_kind=kind,
        materiality_score=score, summary=summary, details=details, impact=impact(feed.document))


def check_feed(feed, *, fetcher=fetch, dry_run=False):
    """Returns {'result': baseline|unchanged|changed|failed|skipped, 'events': n, 'detail': str}."""
    now = timezone.now()
    if feed.feed_type == SourceFeed.FeedType.MANUAL_UPLOAD:
        return {'result': 'skipped', 'events': 0, 'detail': 'Manual-upload source: nothing to fetch; a person uploads new versions.'}
    previous = feed.snapshots.order_by('-fetched_at').first()
    try:
        f = fetcher(feed.endpoint_url)
    except FetchError as exc:
        events = 0
        result = 'skipped' if exc.kind == 'robots' else 'failed'
        # Raise an event only on the transition from working to not working, not every day.
        if not dry_run and previous and feed.last_result not in ('failed', 'skipped'):
            if exc.status in (404, 410):
                _event(feed, SourceChangeEvent.Kind.WITHDRAWAL, 70, f'The page now returns {exc} - it may have '
                       'been removed or moved.', {'http_status': exc.status}, prev=previous)
                events = 1
            elif exc.status in (401, 403) or exc.kind == 'robots':
                _event(feed, SourceChangeEvent.Kind.ACCESS_CHANGE, 40, f'The page can no longer be read automatically '
                       f'({exc}).', {'http_status': exc.status, 'reason': str(exc)}, prev=previous)
                events = 1
        if not dry_run:
            feed.last_checked_at, feed.last_result, feed.last_error = now, result, str(exc)
            feed.save(update_fields=['last_checked_at', 'last_result', 'last_error'])
        return {'result': result, 'events': events, 'detail': str(exc)}

    data, digest = normalize(feed, f)
    if previous and previous.content_hash == digest:
        if not dry_run:
            feed.last_checked_at = feed.last_success_at = now
            feed.last_result, feed.last_error = 'unchanged', ''
            feed.save(update_fields=['last_checked_at', 'last_success_at', 'last_result', 'last_error'])
        return {'result': 'unchanged', 'events': 0, 'detail': ''}
    changes = compare(previous.normalized, data) if previous else []
    detail = (f'{len(data.get("links", []))} document links' if 'links' in data
              else f'{len(data.get("text_lines", []))} text lines' if 'text_lines' in data else f'{len(f.content)} bytes')
    if dry_run:
        return {'result': 'changed' if previous else 'baseline', 'events': len(changes),
                'detail': detail + (' | ' + '; '.join(c[2] for c in changes) if changes else '')}
    with transaction.atomic():
        snap, _ = SourceSnapshot.objects.get_or_create(
            feed=feed, content_hash=digest,
            defaults={'canonical_url': f.url[:1000], 'content_uri': store_raw(f),
                      'http_metadata': {'status': f.status, **f.headers}, 'normalized': data})
        if previous and snap.pk != previous.pk:
            snap.fetched_at = now  # a re-appearing older state becomes the latest again
            snap.save(update_fields=['fetched_at'])
        for kind, score, summary, det in changes:
            _event(feed, kind, score, summary, det, prev=previous, cur=snap)
        feed.last_checked_at = feed.last_success_at = now
        feed.last_result, feed.last_error = ('changed' if previous else 'baseline'), ''
        feed.save(update_fields=['last_checked_at', 'last_success_at', 'last_result', 'last_error'])
    return {'result': feed.last_result, 'events': len(changes), 'detail': detail}


def run_watcher(*, codes=None, trigger='schedule', dry_run=False, fetcher=fetch, include_disabled=False):
    _robots_cache.clear()  # re-read robots.txt once per run (the worker lives for days)
    feeds = SourceFeed.objects.select_related('document').exclude(feed_type=SourceFeed.FeedType.MANUAL_UPLOAD)
    if not include_disabled:
        feeds = feeds.filter(enabled=True)
    if codes:
        feeds = feeds.filter(document__source_code__in=codes)
    run = None if dry_run else WatcherRun.objects.create(trigger=trigger[:40])
    results, failures, changes = [], [], 0
    for feed in feeds.order_by('document__source_code'):
        try:
            res = check_feed(feed, fetcher=fetcher, dry_run=dry_run)
        except Exception as exc:  # one broken feed never stops the run
            logger.exception('watcher.feed_error feed=%s', feed.pk)
            res = {'result': 'failed', 'events': 0, 'detail': f'{type(exc).__name__}: {exc}'[:300]}
        results.append((feed, res))
        changes += res['events']
        if res['result'] == 'failed':
            failures.append({'source_code': feed.document.source_code, 'url': feed.endpoint_url, 'error': res['detail']})
    if run:
        run.feeds_checked, run.changes_detected, run.failure_detail = len(results), changes, failures
        run.status = (WatcherRun.Status.COMPLETE if not failures else
                      WatcherRun.Status.FAILED if len(failures) == len(results) else WatcherRun.Status.PARTIAL_FAILURE)
        run.completed_at = timezone.now()
        run.save()
    return run, results


# -- people decide ------------------------------------------------------------------------

def review_event(event, user, status, note=''):
    if status not in SourceChangeEvent.Status.values or status == SourceChangeEvent.Status.TRIAGED:
        raise ValueError(f'status must be one of {[s for s in SourceChangeEvent.Status.values if s != "triaged"]}.')
    before = event.status
    event.status, event.reviewed_by, event.reviewed_at, event.review_note = status, user, timezone.now(), note
    event.save()
    SourceAuditEvent.objects.create(actor=user.email, action='watcher.event_reviewed', object_type='SourceChangeEvent',
                                    object_id=str(event.pk), before={'status': before}, after={'status': status},
                                    reason=note)


def set_feed_enabled(feed, user, enabled, note=''):
    if feed.enabled != enabled:
        feed.enabled = enabled
        feed.save(update_fields=['enabled'])
        SourceAuditEvent.objects.create(actor=user.email, action='watcher.feed_enabled' if enabled else 'watcher.feed_disabled',
                                        object_type='SourceFeed', object_id=str(feed.pk),
                                        after={'url': feed.endpoint_url, 'enabled': enabled}, reason=note)
