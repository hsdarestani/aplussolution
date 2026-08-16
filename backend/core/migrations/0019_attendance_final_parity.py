from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_self_service_requests'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendancepolicy',
            name='allowed_ip_networks',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='attendancepolicy',
            name='computer_ip_mode',
            field=models.CharField(choices=[('off', 'Aus'), ('warn', 'Hinweis'), ('block', 'Blockieren')], default='off', max_length=10),
        ),
        migrations.AddField(
            model_name='attendanceterminal',
            name='scope_mode',
            field=models.CharField(choices=[('location', 'Bestimmter Einsatzplan'), ('all', 'Alle Einsatzpläne')], default='location', max_length=20),
        ),
        migrations.AlterField(
            model_name='attendanceterminal',
            name='location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='attendance_terminals', to='core.location'),
        ),
    ]
