"""Django system check: a broken AI_PROCESSING_MODE setup is reported when
runserver, migrate or the Celery worker starts -- not when a document fails."""
from django.core.checks import Error, Tags, Warning, register


@register(Tags.compatibility)
def check_ai_processing_mode(app_configs, **kwargs):
    from .services.processing_status import configuration_problems

    errors, warnings = configuration_problems()
    return ([Error(msg, id='extraction.E001') for msg in errors]
            + [Warning(msg, id='extraction.W001') for msg in warnings])
