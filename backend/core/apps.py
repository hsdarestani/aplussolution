from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from . import (  # noqa: F401
            absence_models,
            attendance_models,
            attendance_v4_models,
            attendance_v4_tasks,
            communications_models,
            forecast_models,
            payroll_models,
            portal_models,
            scheduling_models,
            shift_slots,
            communications_signals,
            communications_tasks,
            workplace_models,
        )
