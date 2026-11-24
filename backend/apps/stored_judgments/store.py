"""Find and keep stored answers (models.StoredAnswer) for one run's meter."""
import threading

from django.db import IntegrityError, transaction

from apps.scoring.capability.storage import digest

from .models import StoredAnswer

VERSION = 'reuse-identical-requests-v1'


def request_hash(*, provider, model, policy, tier, kwargs):
    """Everything that decides what the model is asked: provider, model, the frozen settings a request carries
    (effort for its tier, output allowance), and the request itself (prompt, packet, schema, any image)."""
    effort = policy.get('writing_effort') if tier == 'writing' and policy.get('writing_effort') else policy.get('model_effort')
    return digest({'version': VERSION, 'provider': provider, 'model': model, 'tier': tier, 'effort': effort,
                   'gemini_reasoning_effort': policy.get('gemini_reasoning_effort'),
                   'output_tokens': policy.get('output_tokens'),
                   'request': {k: kwargs.get(k) for k in sorted(kwargs) if k != 'timeout'}})


class RunAnswers:
    """One run's view of the store: counts how many times the run has sent each request, so its n-th identical
    request is matched to the n-th stored answer."""

    def __init__(self, run_id):
        self.run_id = run_id
        self._lock = threading.Lock()
        self._seen = {}
        self.reused = 0
        self.stored = 0

    def occurrence(self, key):
        with self._lock:
            number = self._seen.get(key, 0)
            self._seen[key] = number + 1
            return number

    def find(self, key, occurrence):
        row = StoredAnswer.objects.filter(request_hash=key, occurrence=occurrence).only('answer', 'run_id').first()
        if row is None:
            return None
        with self._lock:
            self.reused += 1
        return row

    def keep(self, key, occurrence, *, model, schema_name, answer):
        """Store the model's answer; the first answer stored for a request and occurrence stands."""
        from apps.extraction.usage import DB_WRITE_LOCK
        try:
            with DB_WRITE_LOCK, transaction.atomic():
                StoredAnswer.objects.create(request_hash=key, occurrence=occurrence, model=model,
                                            schema_name=schema_name or '', answer=answer, run_id=self.run_id)
        except IntegrityError:
            return False
        with self._lock:
            self.stored += 1
        return True

    def summary(self):
        return {'version': VERSION, 'reused_answers': self.reused, 'stored_answers': self.stored}
