from django.apps import AppConfig


class ScoringConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.scoring'
    verbose_name = 'Scoring'

    def ready(self):
        from .capability import run_view  # noqa: F401  (signals that keep the runs' display copies)
