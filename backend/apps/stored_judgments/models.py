"""The model's answers to Stage 1 requests, kept so an identical request in a later run gets the same answer.

A stopgap against judge noise (approved 24 Nov 2026 "for now ... as a bandaid"): the same packet sent to the same
model with the same prompt can come back with a different decision, so re-running an unchanged college moved its
scores. With CAPABILITY_STORED_JUDGMENTS on (frozen per run), the first answer to a request is stored, and a later
run that sends exactly that request again (same model, settings, prompt, schema and packet) reuses it instead of
asking. Anything that changes the request (new evidence, a new rubric, another model) asks the model afresh.

Repeated requests inside one run (the agreement passes send the same request two or three times) are told apart by
their occurrence: the second time a run sends a request is matched to the second stored answer, so two passes stay
two independent answers. Everything after the model's answer (quotation checks, credit, tie-breaks, levels) runs
again on every run; only the model's raw structured answer is reused.
"""
from django.db import models


class StoredAnswer(models.Model):
    request_hash = models.CharField(max_length=64)
    occurrence = models.PositiveIntegerField()
    model = models.CharField(max_length=200)
    schema_name = models.CharField(max_length=200, blank=True)
    answer = models.JSONField()
    run_id = models.UUIDField(help_text='The run whose request was answered by the model.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['request_hash', 'occurrence'], name='stored_answer_once')]

    def __str__(self):
        return f'{self.schema_name} {self.request_hash[:12]}#{self.occurrence}'
