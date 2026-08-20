from django.db import migrations
from django.db.models import Q


def archive_historical_wiw_time_entries(apps, schema_editor):
    WorkerProfile = apps.get_model('core', 'WorkerProfile')
    TimeEntry = apps.get_model('core', 'TimeEntry')

    archived_worker_ids = WorkerProfile.objects.filter(
        Q(active=False) | Q(user__is_active=False),
        user__email__endswith='@sync.invalid',
    ).exclude(wiw_user_id__isnull=True).exclude(wiw_user_id='').values_list('id', flat=True)

    # Historical WIW rows remain available for reporting/audit, but they are not
    # operational approval tasks in A+ Workforce. Closing them here keeps the
    # admin attention queue focused on current, native workforce activity.
    TimeEntry.objects.filter(
        worker_id__in=archived_worker_ids,
        approved=False,
    ).update(approved=True)


def noop_reverse(apps, schema_editor):
    # Do not reopen historical approval tasks on rollback.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0010_seed_premium_defaults'),
    ]

    operations = [
        migrations.RunPython(archive_historical_wiw_time_entries, noop_reverse),
    ]
