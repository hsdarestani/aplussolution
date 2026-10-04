from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0046_auev_batch_exports'),
    ]

    operations = [
        migrations.AddField(
            model_name='shiftplanattachment',
            name='visibility',
            field=models.CharField(
                choices=[('all', 'Alle Mitarbeiter'), ('worker', 'Ein Mitarbeiter')],
                default='all',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='shiftplanattachment',
            name='target_worker',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='targeted_shift_plan_attachments',
                to='core.workerprofile',
            ),
        ),
    ]
