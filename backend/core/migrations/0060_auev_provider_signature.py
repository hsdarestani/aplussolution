from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [('core', '0059_historical_worker_employment_type')]

    operations = [
        migrations.AddField(
            model_name='auevsetting',
            name='provider_signature_png',
            field=models.BinaryField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='auevsetting',
            name='provider_signature_approved_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
