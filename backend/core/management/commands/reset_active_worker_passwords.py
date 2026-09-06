from django.core.management.base import BaseCommand

from core.credential_reset import reset_active_worker_passwords, store_reset_batch


class Command(BaseCommand):
    help = 'Reset passwords for every active real worker and keep an encrypted temporary admin retrieval batch.'

    def handle(self, *args, **options):
        credentials = reset_active_worker_passwords()
        batch = store_reset_batch(credentials)
        self.stdout.write(
            self.style.SUCCESS(
                f'ACTIVE_WORKER_PASSWORD_RESET_OK count={len(credentials)} batch_created_at={batch["created_at"]}'
            )
        )
