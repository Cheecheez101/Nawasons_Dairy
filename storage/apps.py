from django.apps import AppConfig


class StorageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "storage"
    verbose_name = "Cold Storage"

    def ready(self):
        # Import signals to register receivers
        from . import signals  # noqa: F401
