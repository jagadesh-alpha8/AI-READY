from django.apps import AppConfig


class ExtractionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.extraction'
    verbose_name = 'Extraction'

    def ready(self):
        from . import checks  # noqa: F401 -- registers the AI_PROCESSING_MODE system check
