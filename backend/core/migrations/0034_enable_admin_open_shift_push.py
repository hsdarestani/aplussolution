from django.db import migrations


def enable_admin_open_shift_push(apps, schema_editor):
    NotificationPushRule = apps.get_model('core', 'NotificationPushRule')
    rule, created = NotificationPushRule.objects.get_or_create(
        key='admin_open_shift',
        defaults={
            'enabled': True,
            'title_template': '{title}',
            'body_template': '{body}',
        },
    )
    if not created and not rule.enabled:
        rule.enabled = True
        rule.save(update_fields=['enabled', 'updated_at'])


def noop_reverse(apps, schema_editor):
    # Do not silently disable a notification family on rollback.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0033_cleanup_spenerhaus_directory'),
    ]

    operations = [
        migrations.RunPython(enable_admin_open_shift_push, noop_reverse),
    ]
