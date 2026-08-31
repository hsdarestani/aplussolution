from copy import copy
from email.utils import parseaddr

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend


def _address(value):
    return parseaddr(value or '')[1].strip().lower()


class WorkerAwareSMTPEmailBackend(SMTPEmailBackend):
    """SMTP backend that can temporarily suppress mail to worker accounts only."""

    def send_messages(self, email_messages):
        messages = list(email_messages or [])
        if not messages:
            return 0
        if getattr(settings, 'WORKER_EMAILS_ENABLED', False):
            return super().send_messages(messages)

        from .models import User

        addresses = {
            _address(value)
            for message in messages
            for value in [*(message.to or []), *(message.cc or []), *(message.bcc or [])]
            if _address(value)
        }
        worker_addresses = {
            email.lower()
            for email in User.objects.filter(
                role=User.Role.WORKER,
                email__in=addresses,
            ).values_list('email', flat=True)
        }

        filtered = []
        for message in messages:
            safe = copy(message)
            safe.to = [value for value in (message.to or []) if _address(value) not in worker_addresses]
            safe.cc = [value for value in (message.cc or []) if _address(value) not in worker_addresses]
            safe.bcc = [value for value in (message.bcc or []) if _address(value) not in worker_addresses]
            if safe.recipients():
                filtered.append(safe)

        if not filtered:
            return 0
        return super().send_messages(filtered)
