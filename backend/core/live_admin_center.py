from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import admin_center_views as base
from .attendance_models import TimeEntryCorrection
from .models import Shift, TimeEntry, WorkerProfile


def _nonempty(field):
    return ~Q(**{f'{field}__isnull': True}) & ~Q(**{field: ''})


def _legacy_wiw_item_keys(items):
    """Return exception keys that belong to imported WIW history.

    Imported data remains in the database for archive/reporting and the final
    controlled cutover. It must not create day-to-day action noise meanwhile.
    """
    shift_ids = set()
    time_entry_ids = set()
    correction_ids = set()
    worker_ids = set()

    for item in items:
        category = item.get('category')
        object_id = item.get('object_id')
        title = item.get('title') or ''
        meta = item.get('meta') or {}

        if category == 'staffing' and object_id:
            shift_ids.add(object_id)
        elif category == 'attendance':
            if title == 'Arbeitszeit noch nicht freigegeben' and object_id:
                time_entry_ids.add(object_id)
            elif title == 'Arbeitszeit-Korrektur wartet' and object_id:
                correction_ids.add(object_id)
            elif title == 'Kein Check-in erfasst' and object_id:
                shift_ids.add(object_id)
            if meta.get('worker_id'):
                worker_ids.add(str(meta['worker_id']))
        elif category == 'documents' and object_id:
            worker_ids.add(object_id)
        elif category == 'requests' and meta.get('worker_id'):
            worker_ids.add(str(meta['worker_id']))

    imported_workers = {
        str(pk)
        for pk in WorkerProfile.objects.filter(id__in=worker_ids)
        .filter(_nonempty('wiw_user_id'))
        .values_list('id', flat=True)
    }
    imported_shifts = {
        str(pk)
        for pk in Shift.objects.filter(id__in=shift_ids)
        .filter(_nonempty('wiw_shift_id'))
        .values_list('id', flat=True)
    }
    imported_entries = {
        str(pk)
        for pk in TimeEntry.objects.filter(id__in=time_entry_ids)
        .filter(_nonempty('wiw_time_id') | _nonempty('worker__wiw_user_id'))
        .values_list('id', flat=True)
    }
    imported_corrections = {
        str(pk)
        for pk in TimeEntryCorrection.objects.filter(id__in=correction_ids)
        .filter(_nonempty('entry__wiw_time_id') | _nonempty('requested_by__wiw_user_id'))
        .values_list('id', flat=True)
    }
    return imported_workers, imported_shifts, imported_entries, imported_corrections


def _is_legacy_wiw_item(item, imported_workers, imported_shifts, imported_entries, imported_corrections):
    category = item.get('category')
    object_id = str(item.get('object_id') or '')
    title = item.get('title') or ''
    meta = item.get('meta') or {}
    worker_id = str(meta.get('worker_id') or '')

    if category == 'integrations' and str(meta.get('provider') or '').lower() == 'wiw':
        return True
    if category == 'staffing':
        return object_id in imported_shifts
    if category == 'documents':
        return object_id in imported_workers
    if category == 'requests':
        return worker_id in imported_workers
    if category == 'attendance':
        if worker_id in imported_workers:
            return True
        if title == 'Kein Check-in erfasst':
            return object_id in imported_shifts
        if title == 'Arbeitszeit noch nicht freigegeben':
            return object_id in imported_entries
        if title == 'Arbeitszeit-Korrektur wartet':
            return object_id in imported_corrections
    return False


@api_view(['GET'])
def admin_exception_center(request):
    denied = base._manager_required(request)
    if denied:
        return denied

    items = base._exception_center_items(timezone.now())
    imported_workers, imported_shifts, imported_entries, imported_corrections = _legacy_wiw_item_keys(items)
    items = [
        item
        for item in items
        if not _is_legacy_wiw_item(
            item,
            imported_workers,
            imported_shifts,
            imported_entries,
            imported_corrections,
        )
    ]

    category = str(request.GET.get('category') or '').strip()
    severity = str(request.GET.get('severity') or '').strip()
    query = str(request.GET.get('q') or '').strip().lower()
    if category and category != 'all':
        allowed = {part.strip() for part in category.split(',') if part.strip()}
        items = [item for item in items if item['category'] in allowed]
    if severity and severity != 'all':
        allowed = {part.strip() for part in severity.split(',') if part.strip()}
        items = [item for item in items if item['severity'] in allowed]
    if query:
        items = [
            item for item in items
            if query in f"{item['title']} {item['message']} {item['category']}".lower()
        ]

    summary = {
        'total': len(items),
        'critical': sum(item['severity'] == 'critical' for item in items),
        'warning': sum(item['severity'] == 'warning' for item in items),
        'info': sum(item['severity'] == 'info' for item in items),
        'by_category': {
            category_name: sum(item['category'] == category_name for item in items)
            for category_name in ['staffing', 'attendance', 'contracts', 'documents', 'integrations', 'requests']
        },
    }
    try:
        limit = min(200, max(1, int(request.GET.get('limit') or 80)))
    except (TypeError, ValueError):
        limit = 80
    items.sort(key=base._sort_value)
    return Response({
        'generated_at': timezone.now(),
        'summary': summary,
        'results': items[:limit],
        'returned': min(len(items), limit),
    })
