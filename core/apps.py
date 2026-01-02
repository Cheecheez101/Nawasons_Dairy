from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from . import signals  # noqa: F401
        self._patch_django_context_copy()

    @staticmethod
    def _patch_django_context_copy():
        """Monkey patch BaseContext.__copy__ for Python 3.14 compatibility."""
        from django.template import context as django_context

        current_copy = django_context.BaseContext.__copy__
        if getattr(current_copy, "__module__", "") != "django.template.context":
            return

        def _safe_copy(self):
            duplicate = self.__class__.__new__(self.__class__)
            duplicate.__dict__ = self.__dict__.copy()
            duplicate.dicts = self.dicts[:]
            return duplicate

        django_context.BaseContext.__copy__ = _safe_copy

