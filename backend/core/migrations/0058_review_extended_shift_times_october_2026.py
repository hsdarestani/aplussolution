"""Review out-of-plan native A+ times auto approved earlier this month.

Do not amend closed historical months, manual manager decisions, imported WIW
evidence or Lexware records. The regular monthly payroll recompute will only
count approved hours in the current/open October period.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import migrations
from django.db.models import F, Q


def review_out_of_plan_time(apps, schema_editor):
    TimeEntry = apps.get_model('core', 'TimeEntry')
    AuditLog = apps.get_model('core', 'AuditLog')
    db = schema_editor.connection.alias

    # Retain already manually reviewed entries; backfill solely routine A+
    # native approvals from the still-open October accounting month.
    candidates = (
        TimeEntry.objects.using(db).filter(
            wiw_time_id__isnull=True,
            clock_out__isnull=False,
            shift_id__isnull=False,
            approved=True,
            approved_by_id__isnull=True,
            clock_in__gte=datetime(2026, 10, 1, tzinfo=ZoneInfo('Europe/Berlin')),
        )
        .filter(Q(clock_in__lt=F('shift__starts_at')) | Q(clock_out__gt=F('shift__ends_at')))
        .exclude(edit_reason__contains='ADMIN_REVIEW:')
        .exclude(edit_reason__startswith='ADMIN_SHIFT_ENTRY:')
    )
    converted = 0
    for entry in candidates.iterator(chunk_size=200):
        if TimeEntry.objects.using(db).filter(
            pk=entry.pk, approved=True, approved_by_id__isnull=True
        ).update(approved=False):
            AuditLog.objects.using(db).create(
                actor_id=None, action='time.outside_plan_reopened',
                object_type='TimeEntry', object_id=str(entry.pk),
                metadata={'reason': 'Outside scheduled start/end', 'automated': True,
                          'month': '2026-10', 'payroll_ledger_unchanged': True},
                ip_address=None,
            )
            converted += 1
    print(f'TIME_OUTSIDE_PLAN_2026_10 requeued_for_admin={converted}', flush=True)


class Migration(migrations.Migration):
    dependencies = [('core', '0057_backfill_completed_native_time_approvals')]
    operations = [migrations.RunPython(review_out_of_plan_time, migrations.RunPython.noop)]
