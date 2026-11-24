from django.apps import AppConfig


class StoredJudgmentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.stored_judgments'
    label = 'stored_judgments'
    verbose_name = 'Stored judgments'
