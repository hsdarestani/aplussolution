from datetime import date, timedelta

from django.core.cache import cache

from core.models import Shift, TimeEntry, WorkerProfile, WorkingTimeAccountRecord
from core.wiw import WhenIWorkClient
from core.wiw_sync import WhenIWorkSynchronizer
from core.working_time import fetch_attendance, sync_working_time

cache.delete(WhenIWorkClient.TOKEN_CACHE_KEY)
cache.delete(WhenIWorkClient.USER_CONTEXT_CACHE_KEY)

client = WhenIWorkClient()
token = client.login(force=True)
context = client.resolve_user_context(token, force=True)
shifts = client.collection('shifts', params={'limit': 5})
times = client.collection('times', params={'limit': 5})

print('WIW_CONTEXT_RESOLVED', bool(context))
print('WIW_SHIFTS_ACCESS', shifts.status_code, len(shifts.items))
print('WIW_TIMES_ACCESS', times.status_code, len(times.items))
assert context
assert shifts.status_code == 200
assert times.status_code == 200

for index, item in enumerate(shifts.items[:3], start=1):
    safe = {
        key: item.get(key)
        for key in (
            'id', 'shift_id', 'start_time', 'end_time', 'start', 'end',
            'starts_at', 'ends_at', 'user_id', 'location_id', 'site_id', 'position_id'
        )
        if key in item
    }
    print('WIW_SHIFT_SHAPE', index, sorted(item.keys()), safe)

today = date.today()
attendance, source, warning = fetch_attendance(
    client,
    today - timedelta(days=1),
    today + timedelta(days=1),
)
print('WIW_ATTENDANCE_PATH', source, len(attendance), bool(warning))

sync_run = WhenIWorkSynchronizer(client=client).sync('full')
print('WIW_FULL_SYNC_STATUS', sync_run.status)
print('WIW_FULL_SYNC_ERRORS', len(sync_run.errors or []))
print(
    'WIW_FULL_SYNC_ERROR_DETAILS',
    [
        {
            'resource': row.get('resource'),
            'error': row.get('error'),
        }
        for row in (sync_run.errors or [])
    ],
)
assert sync_run.status in {'success', 'partial'}

working_log = sync_working_time(date(today.year, 1, 1), today, client=client)
print('WORKING_TIME_SYNC_STATUS', working_log.status)
print('WORKING_TIME_RECORDS_CREATED', working_log.records_count)
print(
    'PRODUCTION_WIW_WORKERS',
    WorkerProfile.objects.exclude(wiw_user_id__isnull=True).exclude(wiw_user_id='').count(),
)
print(
    'PRODUCTION_WIW_SHIFTS',
    Shift.objects.exclude(wiw_shift_id__isnull=True).exclude(wiw_shift_id='').count(),
)
print(
    'PRODUCTION_WIW_TIMES',
    TimeEntry.objects.exclude(wiw_time_id__isnull=True).exclude(wiw_time_id='').count(),
)
print('PRODUCTION_WORKING_TIME_ROWS', WorkingTimeAccountRecord.objects.count())
assert working_log.status in {'ok', 'warning'}
