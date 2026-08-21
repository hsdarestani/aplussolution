from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from . import (  # noqa: F401
            attendance_models,
            portal_models,
            premium_approval_models,
            premium_models,
            premium_signals,
            premium_tasks,
            shift_slots,
        )
        from .smart_docx_integration import install_smart_docx_renderer

        install_smart_docx_renderer()
