from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0039_repair_musa_time_entry_ownership'),
    ]

    operations = [
        migrations.AddField(
            model_name='timeentry',
            name='break_minutes',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
