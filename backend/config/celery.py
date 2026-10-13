import os
from celery import Celery
from celery.signals import worker_ready

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('aios_backend')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@worker_ready.connect
def log_ai_processing_mode(sender=None, **kwargs):
    """First thing in the worker log: which AI mode this worker runs (no keys)."""
    import logging

    from apps.extraction.services.processing_status import configuration_problems, summary_line

    log = logging.getLogger('apps.extraction.mode')
    try:
        log.info('ai.mode %s worker=%s', summary_line(), getattr(sender, 'hostname', '?'))
        errors, warnings = configuration_problems()
        for msg in errors:
            log.error('ai.mode.config_error %s', msg)
        for msg in warnings:
            log.warning('ai.mode.config_warning %s', msg)
    except Exception as exc:  # never stop the worker over a log line
        log.error('ai.mode.describe_failed error=%s', exc)

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')