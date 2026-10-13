"""Stage 3.2: link approved requirements to benchmarks.

link / unlink: only while the benchmark is a draft (a released benchmark's
basis can't change silently), only for requirements whose source version
isn't withdrawn, every change audited.

suggest_benchmarks: explainable ranking, no AI call -- it works without the
AI endpoint and costs nothing. A benchmark scores when its Source Pack
"source basis" names the requirement's authority (UGC, NAAC, NIST ...), and
when the words of the requirement and its source document overlap the
benchmark's title, capability and source basis. Each suggestion says why.
People decide; nothing is linked automatically.
"""
import re

from django.db import transaction

from ..models import Benchmark, BenchmarkRequirement, Requirement, SourceAuditEvent, SourceVersion


class LinkError(Exception):
    pass


STOP = set('''the and for with that this from into such their there these those shall should must will
may have has had are was were been being any all its which where when what who whom also other than then
them they institution institutions university universities college colleges each every per under within
including include includes provide provided provides ensure ensures made make using used use based
including about over more most must least less only same some very can could would being upon'''.split())


def tokens(text):
    return {w for w in re.findall(r'[a-z][a-z0-9-]{3,}', (text or '').lower()) if w not in STOP}


_GENERIC_TITLE_WORDS = {'The', 'Act', 'Rules', 'Regulation', 'Regulations', 'Guidelines', 'Guidance', 'Directions',
                        'Section', 'Under', 'And', 'For', 'Of'}


def title_acronym(title):
    """'The Digital Personal Data Protection Act, 2023' -> 'dpdp' (how the Source Pack names it)."""
    words = [w for w in re.findall(r'\b[A-Z][A-Za-z]+', title.split(',')[0].split('(')[0])
             if w not in _GENERIC_TITLE_WORDS]
    acronym = ''.join(w[0] for w in words).lower()
    return acronym if 3 <= len(acronym) <= 6 else ''


def _authority_aliases(requirement):
    doc = requirement.version.document
    auth = doc.framework.authority
    aliases = {auth.code.lower(), auth.name.lower(), title_acronym(doc.title)}
    aliases |= {a.strip().lower() for a in re.split(r'[/()]', auth.name) if len(a.strip()) >= 3}
    return {a for a in aliases if len(a) >= 3}


def suggest_benchmarks(requirement, limit=5):
    """[{benchmark, score, reasons}] best first; already-linked benchmarks are left out."""
    doc = requirement.version.document
    req_words = tokens(f'{requirement.statement} {requirement.source_quote}')
    doc_words = tokens(doc.title)
    aliases = _authority_aliases(requirement)
    linked = set(requirement.benchmark_links.values_list('benchmark_id', flat=True))
    out = []
    for b in Benchmark.objects.select_related('capability', 'pillar').exclude(pk__in=linked):
        basis = b.source_basis.lower()
        reasons, score = [], 0.0
        named = sorted(a for a in aliases if re.search(rf'\b{re.escape(a)}\b', basis))
        if named:
            score += 3
            reasons.append(f'source basis names {named[0].upper()}')
        topic = sorted(doc_words & tokens(b.source_basis))
        if topic:
            score += 2 * len(topic)
            reasons.append('source basis mentions ' + ', '.join(topic[:3]))
        bench_words = tokens(f'{b.title} {b.capability.definition}')
        overlap = sorted(req_words & bench_words)
        if overlap:
            score += len(overlap)
            reasons.append('shared terms: ' + ', '.join(overlap[:5]))
        if score:
            out.append({'benchmark': b, 'score': round(score, 1), 'reasons': reasons})
    out.sort(key=lambda s: (-s['score'], s['benchmark'].benchmark_code))
    return out[:limit]


def _check_draft(benchmark):
    from .release_lock import lock_message
    if benchmark.status != Benchmark.Status.DRAFT:
        raise LinkError(f'{benchmark.benchmark_code} is {benchmark.status}; its requirements can only change '
                        'in a new draft.')
    if lock_message(benchmark):
        raise LinkError(lock_message(benchmark))


def link(benchmark, requirement, user, *, relationship, note=''):
    if relationship not in BenchmarkRequirement.Relationship.values:
        raise LinkError(f'relationship must be one of {BenchmarkRequirement.Relationship.values}.')
    _check_draft(benchmark)
    if requirement.version.status == SourceVersion.Status.WITHDRAWN:
        raise LinkError(f'{requirement.code} comes from a withdrawn source version.')
    with transaction.atomic():
        obj, created = BenchmarkRequirement.objects.get_or_create(
            benchmark=benchmark, requirement=requirement,
            defaults={'relationship': relationship, 'note': note, 'linked_by': user})
        if not created and (obj.relationship != relationship or obj.note != note):
            before = {'relationship': obj.relationship, 'note': obj.note}
            obj.relationship, obj.note = relationship, note
            obj.save()
            SourceAuditEvent.objects.create(actor=user.email, action='benchmark.link_changed', object_type='Benchmark',
                                            object_id=str(benchmark.pk), before=before,
                                            after={'requirement': requirement.code, 'relationship': relationship},
                                            reason=note)
        elif created:
            SourceAuditEvent.objects.create(actor=user.email, action='benchmark.linked', object_type='Benchmark',
                                            object_id=str(benchmark.pk),
                                            after={'requirement': requirement.code, 'relationship': relationship},
                                            reason=note)
    return obj


def unlink(benchmark, requirement, user, *, note=''):
    _check_draft(benchmark)
    deleted, _ = BenchmarkRequirement.objects.filter(benchmark=benchmark, requirement=requirement).delete()
    if not deleted:
        raise LinkError(f'{requirement.code} is not linked to {benchmark.benchmark_code}.')
    SourceAuditEvent.objects.create(actor=user.email, action='benchmark.unlinked', object_type='Benchmark',
                                    object_id=str(benchmark.pk), after={'requirement': requirement.code}, reason=note)


def unlinked_requirements():
    return Requirement.objects.filter(benchmark_links__isnull=True).select_related('version__document')
