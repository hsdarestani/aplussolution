from django.db import migrations


CONTRACT_TEXT = 'Marthas Finest GmbH, Kurt-Schumacher Straße 23, 60311 Frankfurt am Main, Deutschland'


def apply_contract_text(apps, schema_editor):
    ClientCompany = apps.get_model('core', 'ClientCompany')
    AuevSetting = apps.get_model('core', 'AuevSetting')

    for client in ClientCompany.objects.all():
        name = (client.name or '').casefold()
        if 'martha' not in name:
            continue

        setting, _ = AuevSetting.objects.get_or_create(client=client)
        setting.client_contract_text = CONTRACT_TEXT
        if not setting.file_label:
            setting.file_label = 'Marthas'
            setting.save(update_fields=['client_contract_text', 'file_label', 'updated_at'])
        else:
            setting.save(update_fields=['client_contract_text', 'updated_at'])


def reverse_contract_text(apps, schema_editor):
    ClientCompany = apps.get_model('core', 'ClientCompany')
    AuevSetting = apps.get_model('core', 'AuevSetting')

    for client in ClientCompany.objects.all():
        name = (client.name or '').casefold()
        if 'martha' not in name:
            continue
        setting = AuevSetting.objects.filter(client=client).first()
        if not setting:
            continue
        if setting.client_contract_text == CONTRACT_TEXT:
            setting.client_contract_text = ''
            setting.save(update_fields=['client_contract_text', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0049_fix_remaining_anu_birth_dates'),
    ]

    operations = [
        migrations.RunPython(apply_contract_text, reverse_contract_text),
    ]
