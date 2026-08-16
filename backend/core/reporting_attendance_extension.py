from . import reporting_service
from .attendance_final_service import clock_event_audit
from .models import TimeEntry


AUDIT_FIELDS = {
    'clock_in_ip': ('IP Einstempeln', False),
    'clock_out_ip': ('IP Ausstempeln', False),
    'clock_in_method': ('Methode Einstempeln', False),
    'clock_out_method': ('Methode Ausstempeln', False),
    'clock_in_lat': ('Breitengrad Einstempeln', False),
    'clock_in_lng': ('Längengrad Einstempeln', False),
    'clock_out_lat': ('Breitengrad Ausstempeln', False),
    'clock_out_lng': ('Längengrad Ausstempeln', False),
}


_base_time_loader = reporting_service.SOURCE_LOADERS['times']


def _audited_time_rows(user, filters):
    rows = _base_time_loader(user, filters)
    ids = [row.get('id') for row in rows if row.get('id')]
    if not ids:
        return rows
    entries = TimeEntry.objects.filter(pk__in=ids).prefetch_related('clock_events')
    audit_by_id = {str(entry.id): clock_event_audit(entry) for entry in entries}
    for row in rows:
        row.update(audit_by_id.get(str(row.get('id')), {}))
    return rows


reporting_service.FIELD_CATALOG['times'].update(AUDIT_FIELDS)
reporting_service.SOURCE_LOADERS['times'] = _audited_time_rows
