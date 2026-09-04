from django.apps import AppConfig


class VectorStoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.vector_store'
    label = 'vector_store'
    verbose_name = 'Vector Store'
