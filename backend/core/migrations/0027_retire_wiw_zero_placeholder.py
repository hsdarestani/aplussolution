from django.db import migrations
from django.db.models import Q


def retire_wiw_zero_placeholder(apps, schema_editor):
    User = apps.get_model('core', 'User')
    WorkerProfile = apps.get_model('core', 'WorkerProfile')
    Shift = apps.get_model('core', 'Shift')
    ShiftSlot = apps.get_model('core', 'ShiftSlot')

    workers = WorkerProfile.objects.filter(
        Q(wiw_user_id='0') | Q(user__email__iexact='wiw-0@sync.invalid')
    )
    worker_ids = list(workers.values_list('pk', flat=True))

    if worker_ids:
        # WIW user id 0 is the unassigned/OpenShift sentinel, never a real worker.
        # Preserve the imported shifts but detach the fake assignment so the shift
        # becomes an ordinary published OpenShift again.
        Shift.objects.filter(worker_id__in=worker_ids).exclude(status='cancelled').update(
            worker=None,
            is_open=True,
            status='published',
        )
        ShiftSlot.objects.filter(worker_id__in=worker_ids).exclude(status='cancelled').update(
            worker=None,
            status='open',
            claimed_at=None,
        )
        workers.update(active=False)

    User.objects.filter(
        Q(wiw_id='0') | Q(email__iexact='wiw-0@sync.invalid')
    ).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0026_restore_inactive_position_choices'),
    ]

    operations = [
        migrations.RunPython(retire_wiw_zero_placeholder, migrations.RunPython.noop),
    ]
