from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from . import attendance_models, forecast_models, portal_models, scheduling_models, shift_slots  # noqa: F401
