import traceback

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test import RequestFactory

from core.client_order_planning import plan_client_order
from core.models import ClientOrder, User


class Command(BaseCommand):
    help = 'Run a rollback-only planning probe against a real client order.'

    def add_arguments(self, parser):
        parser.add_argument('--title', default='QA Client Order')

    def handle(self, *args, **options):
        title = options['title']
        order = (
            ClientOrder.objects.select_related('client', 'location')
            .filter(title=title)
            .order_by('-created_at')
            .first()
        )
        if not order:
            self.stdout.write(self.style.WARNING(f'ORDER_PROBE skipped: no order titled {title!r}'))
            return

        admin = User.objects.filter(role=User.Role.ADMIN, is_active=True).order_by('created_at').first()
        if not admin:
            raise CommandError('ORDER_PROBE failed: no active admin user found')

        request = RequestFactory().post('/internal/order-planning-probe')
        request.user = admin
        request.META['REMOTE_ADDR'] = '127.0.0.1'

        self.stdout.write(
            'ORDER_PROBE input '
            f'id={order.id} status={order.status} client={order.client_id} '
            f'location={order.location_id} requested_staff={order.requested_staff} '
            f'functions_type={type(order.functions).__name__} functions={order.functions!r}'
        )

        try:
            with transaction.atomic():
                planned_order, shift, created = plan_client_order(order.id, request)
                self.stdout.write(
                    self.style.SUCCESS(
                        'ORDER_PROBE success '
                        f'created={created} order_status={planned_order.status} '
                        f'shift={shift.id} position={shift.position_id} required_count={shift.required_count}'
                    )
                )
                transaction.set_rollback(True)
        except Exception as exc:
            self.stderr.write('ORDER_PROBE exception: ' + repr(exc))
            self.stderr.write(traceback.format_exc())
            raise CommandError(f'ORDER_PROBE failed: {exc.__class__.__name__}: {exc}') from exc
