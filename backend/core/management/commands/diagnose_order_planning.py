import json
import traceback

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.test import APIRequestFactory, force_authenticate

from core.models import ClientOrder, User
from core.searchable_views import OrderViewSet


class Command(BaseCommand):
    help = 'Run a rollback-only PATCH /orders/:id/ planning probe against a real client order.'

    def add_arguments(self, parser):
        parser.add_argument('--title', default='QA Client Order')

    def handle(self, *args, **options):
        title = options['title']
        order = (
            ClientOrder.objects.select_related('client', 'location')
            .prefetch_related('shifts')
            .filter(title=title)
            .order_by('-created_at')
            .first()
        )
        if not order:
            self.stdout.write(self.style.WARNING(f'ORDER_API_PROBE skipped: no order titled {title!r}'))
            return

        admin = User.objects.filter(role=User.Role.ADMIN, is_active=True).order_by('date_joined', 'id').first()
        if not admin:
            raise CommandError('ORDER_API_PROBE failed: no active admin user found')

        shifts = list(
            order.shifts.order_by('starts_at').values(
                'id', 'status', 'is_open', 'required_count', 'position_id', 'location_id'
            )
        )
        self.stdout.write(
            'ORDER_API_PROBE input '
            f'id={order.id} status={order.status} client={order.client_id} '
            f'location={order.location_id} requested_staff={order.requested_staff} '
            f'functions_type={type(order.functions).__name__} functions={order.functions!r} '
            f'existing_shifts={json.dumps(shifts, default=str, ensure_ascii=False)}'
        )

        factory = APIRequestFactory()
        request = factory.patch(
            f'/api/orders/{order.id}/',
            {'status': ClientOrder.Status.CONFIRMED},
            format='json',
        )
        force_authenticate(request, user=admin)
        view = OrderViewSet.as_view({'patch': 'partial_update'})

        try:
            with transaction.atomic():
                response = view(request, pk=str(order.id))
                response.render()
                payload = getattr(response, 'data', None)
                self.stdout.write(
                    'ORDER_API_PROBE response '
                    f'status_code={response.status_code} '
                    f'data={json.dumps(payload, default=str, ensure_ascii=False)}'
                )
                if response.status_code >= 400:
                    raise RuntimeError(f'PATCH returned HTTP {response.status_code}: {payload!r}')
                transaction.set_rollback(True)
        except Exception as exc:
            self.stderr.write('ORDER_API_PROBE exception: ' + repr(exc))
            self.stderr.write(traceback.format_exc())
            raise CommandError(f'ORDER_API_PROBE failed: {exc.__class__.__name__}: {exc}') from exc

        self.stdout.write(self.style.SUCCESS('ORDER_API_PROBE success: PATCH path completed and transaction was rolled back.'))
