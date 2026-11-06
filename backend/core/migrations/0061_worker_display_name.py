from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('core', '0060_auev_provider_signature')]
    operations = [migrations.AddField(model_name='workerprofile', name='display_name', field=models.CharField(max_length=120, blank=True, default=''))]
