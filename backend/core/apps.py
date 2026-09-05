from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from . import (  # noqa: F401
            attendance_models,
            document_source_recovery,
            location_client_consistency,
            notification_copy,
            operational_notifications,
            portal_models,
            premium_approval_models,
            premium_models,
            premium_signals,
            premium_tasks,
            push_models,
            push_signals,
            shift_slots,
            wiw_name_protection,
        )
        from .smart_docx_integration import install_smart_docx_renderer
        from .smartdocs_contract_integration import install_smartdocs_contract_renderer
        from .wiw_position_protection import install_wiw_position_protection

        install_smart_docx_renderer()
        install_smartdocs_contract_renderer()
        install_wiw_position_protection()
