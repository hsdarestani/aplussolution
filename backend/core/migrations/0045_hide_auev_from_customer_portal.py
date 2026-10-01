from django.db import migrations


def hide_old_auev_notifications(apps, schema_editor):
    Notification = apps.get_model('core', 'Notification')
    Contract = apps.get_model('core', 'Contract')
    ContractTemplate = apps.get_model('core', 'ContractTemplate')

    Notification.objects.filter(
        user__role='client',
        kind__startswith='client-contract-generated-',
    ).delete()

    contract_ids = Contract.objects.filter(
        template__kind='client_auev',
    ).values_list('id', flat=True)
    for contract_id in contract_ids:
        Notification.objects.filter(
            user__role='client',
            kind=f'contract-sent-{contract_id}',
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0044_auev_settings'),
    ]

    operations = [
        migrations.RunPython(hide_old_auev_notifications, migrations.RunPython.noop),
    ]
