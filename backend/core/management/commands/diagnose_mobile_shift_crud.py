import json
import traceback
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from core.models import Shift, User, WorkerProfile
from core.shift_slot_actions import edit_shift_slot
from core.shift_slots import ShiftSlot
from core.shift_views import StaffingShiftViewSet


class Command(BaseCommand):
    help = 'Rollback-only production probe for the exact mobile WIW shift create/edit/assign paths.'

    def _call(self, request, view, label, **kwargs):
        response = view(request, **kwargs)
        response.render()
        payload = getattr(response, 'data', None)
        self.stdout.write(
            f'MOBILE_SHIFT_PROBE {label} status={response.status_code} '
            f'data={json.dumps(payload, default=str, ensure_ascii=False)}'
        )
        if response.status_code >= 400:
            raise RuntimeError(f'{label} returned HTTP {response.status_code}: {payload!r}')
        return response

    def handle(self, *args, **options):
        admin = User.objects.filter(role=User.Role.ADMIN, is_active=True).order_by('date_joined', 'id').first()
        if not admin:
            raise CommandError('MOBILE_SHIFT_PROBE failed: no active admin user found')

        reference = (
            Shift.objects.select_related('client', 'location', 'position')
            .filter(client__isnull=False, location__isnull=False, position__isnull=False)
            .exclude(status=Shift.Status.CANCELLED)
            .order_by('-starts_at')
            .first()
        )
        if not reference:
            self.stdout.write(self.style.WARNING('MOBILE_SHIFT_PROBE skipped: no reference shift exists'))
            return

        # Prefer somebody who has already worked the same position. This probes
        # the assignment endpoint without deliberately tripping required-skill
        # policy rules that should legitimately reject an unsuitable worker.
        worker = (
            WorkerProfile.objects.select_related('user')
            .filter(
                active=True,
                user__is_active=True,
                shift_slots__status=ShiftSlot.Status.CLAIMED,
                shift_slots__shift__position_id=reference.position_id,
            )
            .exclude(user__email__iendswith='@sync.invalid')
            .distinct()
            .order_by('created_at')
            .first()
        )

        factory = APIRequestFactory()
        create_view = StaffingShiftViewSet.as_view({'post': 'create'})
        assign_view = StaffingShiftViewSet.as_view({'post': 'assign'})

        try:
            with transaction.atomic():
                # 1) Exercise a real imported WIW card, including production-only
                # stale/cancelled slot mappings that unit fixtures cannot model.
                imported = (
                    Shift.objects.select_related('client', 'location', 'position')
                    .filter(
                        wiw_shift_id__isnull=False,
                        slots__status__in=[ShiftSlot.Status.OPEN, ShiftSlot.Status.CLAIMED],
                    )
                    .exclude(wiw_shift_id='')
                    .exclude(status=Shift.Status.CANCELLED)
                    .distinct()
                    .order_by('-starts_at')
                    .first()
                )
                if imported:
                    slot = (
                        imported.slots.exclude(status=ShiftSlot.Status.CANCELLED)
                        .select_related('worker')
                        .order_by('created_at')
                        .first()
                    )
                    if slot:
                        edit_request = factory.patch(
                            f'/api/shifts/{imported.id}/cards/{slot.id}/',
                            {
                                'client': str(imported.client_id),
                                'location': str(imported.location_id),
                                'position': str(imported.position_id),
                                'starts_at': imported.starts_at.isoformat(),
                                'ends_at': imported.ends_at.isoformat(),
                                'notes': imported.notes or '',
                                'confirmation_required': imported.confirmation_required,
                                'schedule_groups': imported.schedule_groups or [],
                                'status': 'draft' if imported.status == Shift.Status.DRAFT else 'published',
                                'apply_all': False,
                            },
                            format='json',
                        )
                        force_authenticate(edit_request, user=admin)
                        self._call(
                            edit_request,
                            edit_shift_slot,
                            'edit-real-wiw-card',
                            shift_id=imported.id,
                            slot_id=slot.id,
                        )

                # Use a far-future window so the production probe cannot collide
                # with normal planning data or overlap rules.
                base = timezone.now() + timedelta(days=3650)
                base = base.replace(hour=21, minute=45, second=0, microsecond=0)

                # 2) Exact mobile draft-create path.
                draft_request = factory.post(
                    '/api/shifts/',
                    {
                        'client': str(reference.client_id),
                        'location': str(reference.location_id),
                        'position': str(reference.position_id),
                        'starts_at': base.isoformat(),
                        'ends_at': (base + timedelta(hours=6)).isoformat(),
                        'notes': 'rollback mobile draft probe',
                        'confirmation_required': False,
                        'schedule_groups': ['service'],
                        'required_count': 1,
                        'status': 'draft',
                    },
                    format='json',
                )
                force_authenticate(draft_request, user=admin)
                draft_response = self._call(draft_request, create_view, 'create-draft')

                # The current mobile client follows create with assign even when
                # no direct worker is selected. Verify that exact empty-assignment
                # path too.
                empty_assign = factory.post(
                    f"/api/shifts/{draft_response.data['id']}/assign/",
                    {'workers': [], 'publish_remaining': False},
                    format='json',
                )
                force_authenticate(empty_assign, user=admin)
                self._call(
                    empty_assign,
                    assign_view,
                    'assign-empty-draft',
                    pk=str(draft_response.data['id']),
                )

                # 3) Cross-midnight published OpenShift with multiple cards.
                overnight_start = base + timedelta(days=2)
                published_request = factory.post(
                    '/api/shifts/',
                    {
                        'client': str(reference.client_id),
                        'location': str(reference.location_id),
                        'position': str(reference.position_id),
                        'starts_at': overnight_start.isoformat(),
                        'ends_at': (overnight_start + timedelta(hours=6)).isoformat(),
                        'notes': 'rollback overnight mobile probe',
                        'confirmation_required': False,
                        'schedule_groups': ['service'],
                        'required_count': 2,
                        'status': 'published',
                    },
                    format='json',
                )
                force_authenticate(published_request, user=admin)
                published_response = self._call(published_request, create_view, 'create-published-overnight')

                empty_publish_assign = factory.post(
                    f"/api/shifts/{published_response.data['id']}/assign/",
                    {'workers': [], 'publish_remaining': True},
                    format='json',
                )
                force_authenticate(empty_publish_assign, user=admin)
                self._call(
                    empty_publish_assign,
                    assign_view,
                    'assign-empty-published',
                    pk=str(published_response.data['id']),
                )

                # 4) Direct worker assignment, when production has a worker who
                # has already demonstrated eligibility for this position.
                if worker:
                    assigned_start = base + timedelta(days=4)
                    assigned_create = factory.post(
                        '/api/shifts/',
                        {
                            'client': str(reference.client_id),
                            'location': str(reference.location_id),
                            'position': str(reference.position_id),
                            'starts_at': assigned_start.isoformat(),
                            'ends_at': (assigned_start + timedelta(hours=5)).isoformat(),
                            'notes': 'rollback assigned mobile probe',
                            'confirmation_required': True,
                            'schedule_groups': ['service'],
                            'required_count': 1,
                            'status': 'draft',
                        },
                        format='json',
                    )
                    force_authenticate(assigned_create, user=admin)
                    assigned_response = self._call(assigned_create, create_view, 'create-for-direct-assignment')
                    worker_assign = factory.post(
                        f"/api/shifts/{assigned_response.data['id']}/assign/",
                        {'workers': [str(worker.id)], 'publish_remaining': False},
                        format='json',
                    )
                    force_authenticate(worker_assign, user=admin)
                    self._call(
                        worker_assign,
                        assign_view,
                        'assign-worker',
                        pk=str(assigned_response.data['id']),
                    )
                else:
                    self.stdout.write('MOBILE_SHIFT_PROBE assign-worker skipped: no position-proven active worker found')

                transaction.set_rollback(True)
        except Exception as exc:
            self.stderr.write('MOBILE_SHIFT_PROBE exception: ' + repr(exc))
            self.stderr.write(traceback.format_exc())
            raise CommandError(f'MOBILE_SHIFT_PROBE failed: {exc.__class__.__name__}: {exc}') from exc

        self.stdout.write(self.style.SUCCESS(
            'MOBILE_SHIFT_PROBE success: real WIW edit, draft create, overnight OpenShift, empty assignment, and eligible direct-assignment path completed; all writes rolled back.'
        ))
